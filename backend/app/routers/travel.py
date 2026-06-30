import unicodedata

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit, routing, travel as travel_module
from ..database import get_db
from ..deps import assert_period_open, get_current_user, get_period
from ..models import Travel, TravelLeg, User
from ..schemas import (
    BulkTravelCreate, PerDiemRates, TravelCreate, TravelLegCreate,
    TravelLegOut, TravelLegUpdate, TravelOut, TravelUpdate,
)

router = APIRouter(prefix="/api", tags=["travel"])

_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _leg_out(leg: TravelLeg) -> TravelLegOut:
    return TravelLegOut(
        id=leg.id,
        travel_id=leg.travel_id,
        order_idx=leg.order_idx,
        from_place=leg.from_place,
        to_place=leg.to_place,
        transport=leg.transport,
        depart_time=leg.depart_time,
        arrive_time=leg.arrive_time,
        distance_km=float(leg.distance_km) if leg.distance_km is not None else None,
        duration_min=leg.duration_min,
        expense=float(leg.expense) if leg.expense is not None else None,
        per_diem=float(leg.per_diem) if leg.per_diem is not None else None,
    )


def serialize(t: Travel, rates: dict) -> TravelOut:
    pd = travel_module.effective_per_diem(t, rates)
    first_depart, last_arrive = travel_module._leg_times(t)
    comp = travel_module.computed_per_diem(
        t.trip_date, t.end_date, first_depart, last_arrive, rates
    )
    km_list = [float(leg.distance_km) for leg in t.legs if leg.distance_km is not None]
    first_depart, last_arrive = travel_module._leg_times(t)
    return TravelOut(
        id=t.id,
        period_id=t.period_id,
        traveller_name=t.traveller_name,
        traveller_address=t.traveller_address,
        trip_date=t.trip_date,
        end_date=t.end_date,
        purpose=t.purpose,
        per_diem=float(pd),
        per_diem_computed=float(comp),
        duration_hours=travel_module.duration_hours(
            t.trip_date, t.end_date, first_depart, last_arrive
        ),
        total_km=round(sum(km_list), 2) if km_list else None,
        legs=[_leg_out(leg) for leg in t.legs],
    )


def _create_legs(db: Session, travel_id: int, legs: list[TravelLegCreate]) -> None:
    for i, leg_data in enumerate(legs):
        data = leg_data.model_dump()
        if "order_idx" not in data or data["order_idx"] == 0:
            data["order_idx"] = i
        leg = TravelLeg(travel_id=travel_id, **data)
        db.add(leg)
        db.flush()
        routing.auto_route(db, leg)


# ---- Per-diem rates ----

@router.get("/travel/per-diem-rates", response_model=PerDiemRates)
def get_per_diem_rates(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return PerDiemRates(**travel_module.get_rates(db))


@router.patch("/travel/per-diem-rates", response_model=PerDiemRates)
def set_per_diem_rates(
    body: PerDiemRates,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    saved = travel_module.set_rates(db, body.model_dump())
    audit.record(db, user, "update", "setting", None, "per-diem rates")
    db.commit()
    return PerDiemRates(**saved)


# ---- Routing key ----

class RoutingKeyStatus(BaseModel):
    configured: bool


class RoutingKeyUpdate(BaseModel):
    key: str


@router.get("/travel/routing-key", response_model=RoutingKeyStatus)
def get_routing_key_status(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return RoutingKeyStatus(configured=routing.get_api_key(db) is not None)


@router.patch("/travel/routing-key", response_model=RoutingKeyStatus)
def set_routing_key(
    body: RoutingKeyUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not body.key.strip():
        raise HTTPException(status_code=422, detail="Key must not be empty")
    routing.set_api_key(db, body.key)
    audit.record(db, user, "update", "setting", None, "ors_api_key")
    db.commit()
    return RoutingKeyStatus(configured=True)


# ---- Trips ----

@router.get("/periods/{period_id}/travels", response_model=list[TravelOut])
def list_travels(
    period_id: int,
    name: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    get_period(db, period_id)
    stmt = select(Travel).where(Travel.period_id == period_id)
    if name:
        stmt = stmt.where(Travel.traveller_name == name)
    stmt = stmt.order_by(Travel.traveller_name, Travel.trip_date, Travel.id)
    rates = travel_module.get_rates(db)
    return [serialize(t, rates) for t in db.scalars(stmt)]


@router.get("/periods/{period_id}/travel-names", response_model=list[str])
def list_travel_names(
    period_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    get_period(db, period_id)
    rows = db.scalars(
        select(Travel.traveller_name)
        .where(Travel.period_id == period_id, Travel.traveller_name != "")
        .distinct()
        .order_by(Travel.traveller_name)
    ).all()
    return list(rows)


@router.post("/periods/{period_id}/travels", response_model=TravelOut, status_code=201)
def create_travel(
    period_id: int,
    payload: TravelCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    period = get_period(db, period_id)
    assert_period_open(period)
    t = Travel(period_id=period_id, **payload.model_dump(exclude={"legs"}))
    db.add(t)
    db.flush()
    _create_legs(db, t.id, payload.legs)
    audit.record(db, user, "create", "travel", t.id, f"{t.traveller_name} {t.trip_date}")
    db.commit()
    db.refresh(t)
    return serialize(t, travel_module.get_rates(db))


@router.post("/periods/{period_id}/travels/bulk", response_model=list[TravelOut], status_code=201)
def bulk_create_travels(
    period_id: int,
    payload: BulkTravelCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    period = get_period(db, period_id)
    assert_period_open(period)
    header = {k: v for k, v in payload.model_dump(exclude={"legs", "dates"}).items()
              if k != "trip_date"}
    created: list[Travel] = []
    for d in sorted(set(payload.dates)):
        t = Travel(period_id=period_id, trip_date=d, end_date=None, **header)
        db.add(t)
        created.append(t)
    db.flush()
    for t in created:
        _create_legs(db, t.id, payload.legs)
    audit.record(db, user, "create", "travel", None,
                 f"bulk {len(created)} trips ({payload.traveller_name})")
    db.commit()
    rates = travel_module.get_rates(db)
    for t in created:
        db.refresh(t)
    return [serialize(t, rates) for t in created]


@router.post("/travels/{travel_id}/duplicate", response_model=TravelOut, status_code=201)
def duplicate_travel(
    travel_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    src = db.get(Travel, travel_id)
    if src is None:
        raise HTTPException(status_code=404, detail="Trip not found")
    assert_period_open(get_period(db, src.period_id))
    clone = Travel(
        period_id=src.period_id,
        traveller_name=src.traveller_name, traveller_address=src.traveller_address,
        trip_date=src.trip_date, end_date=src.end_date, purpose=src.purpose,
    )
    db.add(clone)
    db.flush()
    for leg in src.legs:
        db.add(TravelLeg(
            travel_id=clone.id, order_idx=leg.order_idx,
            from_place=leg.from_place, to_place=leg.to_place, transport=leg.transport,
            depart_time=leg.depart_time, arrive_time=leg.arrive_time,
            distance_km=leg.distance_km, duration_min=leg.duration_min,
            expense=leg.expense, per_diem=leg.per_diem,
        ))
    audit.record(db, user, "create", "travel", clone.id, f"duplicate of {src.id}")
    db.commit()
    db.refresh(clone)
    return serialize(clone, travel_module.get_rates(db))


@router.patch("/travels/{travel_id}", response_model=TravelOut)
def update_travel(
    travel_id: int,
    payload: TravelUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    t = db.get(Travel, travel_id)
    if t is None:
        raise HTTPException(status_code=404, detail="Trip not found")
    assert_period_open(get_period(db, t.period_id))
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(t, key, value)
    audit.record(db, user, "update", "travel", t.id, f"{t.traveller_name} {t.trip_date}")
    db.commit()
    db.refresh(t)
    return serialize(t, travel_module.get_rates(db))


@router.delete("/travels/{travel_id}", status_code=204)
def delete_travel(
    travel_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    t = db.get(Travel, travel_id)
    if t is None:
        raise HTTPException(status_code=404, detail="Trip not found")
    assert_period_open(get_period(db, t.period_id))
    audit.record(db, user, "delete", "travel", t.id, f"{t.traveller_name} {t.trip_date}")
    db.delete(t)
    db.commit()


# ---- Legs ----

def _get_leg_and_trip(leg_id: int, db: Session) -> tuple[TravelLeg, Travel]:
    leg = db.get(TravelLeg, leg_id)
    if leg is None:
        raise HTTPException(status_code=404, detail="Leg not found")
    t = db.get(Travel, leg.travel_id)
    return leg, t


@router.post("/travels/{travel_id}/legs", response_model=TravelOut, status_code=201)
def add_leg(
    travel_id: int,
    payload: TravelLegCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    t = db.get(Travel, travel_id)
    if t is None:
        raise HTTPException(status_code=404, detail="Trip not found")
    assert_period_open(get_period(db, t.period_id))
    next_idx = max((leg.order_idx for leg in t.legs), default=-1) + 1
    data = payload.model_dump()
    data.setdefault("order_idx", next_idx)
    leg = TravelLeg(travel_id=travel_id, **data)
    db.add(leg)
    db.flush()
    routing.auto_route(db, leg)
    audit.record(db, user, "create", "travel_leg", leg.id,
                 f"{leg.from_place}→{leg.to_place} (trip {travel_id})")
    db.commit()
    db.refresh(t)
    return serialize(t, travel_module.get_rates(db))


@router.patch("/travel-legs/{leg_id}", response_model=TravelOut)
def update_leg(
    leg_id: int,
    payload: TravelLegUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    leg, t = _get_leg_and_trip(leg_id, db)
    assert_period_open(get_period(db, t.period_id))
    old_route = (leg.from_place, leg.to_place, leg.transport)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(leg, key, value)
    if (leg.from_place, leg.to_place, leg.transport) != old_route:
        routing.auto_route(db, leg)
    db.commit()
    db.refresh(t)
    return serialize(t, travel_module.get_rates(db))


@router.delete("/travel-legs/{leg_id}", response_model=TravelOut)
def delete_leg(
    leg_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    leg, t = _get_leg_and_trip(leg_id, db)
    assert_period_open(get_period(db, t.period_id))
    db.delete(leg)
    db.commit()
    db.refresh(t)
    return serialize(t, travel_module.get_rates(db))


@router.post("/travel-legs/{leg_id}/route", response_model=TravelOut)
def recalculate_leg_route(
    leg_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    leg, t = _get_leg_and_trip(leg_id, db)
    if not routing.get_api_key(db):
        raise HTTPException(status_code=422, detail="No routing API key configured")
    if not routing.auto_route(db, leg):
        raise HTTPException(
            status_code=422,
            detail="Could not calculate route — check from/to place names and transport type"
        )
    db.commit()
    db.refresh(t)
    return serialize(t, travel_module.get_rates(db))


# ---- Export ----

def _ascii(s: str) -> str:
    decomposed = unicodedata.normalize("NFKD", s)
    out = "".join(c for c in decomposed if not unicodedata.combining(c) and ord(c) < 128)
    return "".join(c if c.isalnum() else "_" for c in out).strip("_") or "report"


@router.get("/periods/{period_id}/travels/export")
def export_travels(
    period_id: int,
    name: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    period = get_period(db, period_id)
    travels = db.scalars(
        select(Travel).where(Travel.period_id == period_id, Travel.traveller_name == name)
    ).all()
    if not travels:
        raise HTTPException(status_code=404, detail="No trips for that person in this month")
    address = next((t.traveller_address for t in travels if t.traveller_address), "")
    rates = travel_module.get_rates(db)
    data = travel_module.build_xlsx(name, address, period.year, period.month, travels, rates)

    month_name = travel_module._SK_MONTHS.get(period.month, str(period.month))
    fname = _ascii(f"Cestovne_{month_name}_{period.year}_{name}") + ".xlsx"
    return Response(
        content=data,
        media_type=_XLSX_MIME,
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
