import unicodedata

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit, travel
from ..database import get_db
from ..deps import assert_period_open, get_current_user, get_period
from ..models import Travel, User
from ..schemas import PerDiemRates, TravelCreate, TravelOut, TravelUpdate

router = APIRouter(prefix="/api", tags=["travel"])

_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def serialize(t: Travel, rates: dict) -> TravelOut:
    pd = travel.effective_per_diem(t, rates)
    comp = travel.computed_per_diem(t.depart_time, t.return_arrive_time, rates)
    return TravelOut(
        id=t.id,
        period_id=t.period_id,
        traveller_name=t.traveller_name,
        traveller_address=t.traveller_address,
        trip_date=t.trip_date,
        from_place=t.from_place,
        to_place=t.to_place,
        purpose=t.purpose,
        depart_time=t.depart_time,
        arrive_time=t.arrive_time,
        return_depart_time=t.return_depart_time,
        return_arrive_time=t.return_arrive_time,
        transport=t.transport,
        per_diem_override=t.per_diem_override,
        per_diem=float(pd),
        per_diem_computed=float(comp),
        duration_hours=travel.duration_hours(t.depart_time, t.return_arrive_time),
    )


@router.get("/travel/per-diem-rates", response_model=PerDiemRates)
def get_per_diem_rates(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return PerDiemRates(**travel.get_rates(db))


@router.patch("/travel/per-diem-rates", response_model=PerDiemRates)
def set_per_diem_rates(
    body: PerDiemRates,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    saved = travel.set_rates(db, body.model_dump())
    audit.record(db, user, "update", "setting", None, "per-diem rates")
    db.commit()
    return PerDiemRates(**saved)


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
    rates = travel.get_rates(db)
    return [serialize(t, rates) for t in db.scalars(stmt)]


@router.get("/periods/{period_id}/travel-names", response_model=list[str])
def list_travel_names(
    period_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Distinct traveller names in this month (for the export picker)."""
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
    t = Travel(period_id=period_id, **payload.model_dump())
    db.add(t)
    db.flush()
    audit.record(db, user, "create", "travel", t.id, f"{t.traveller_name} {t.trip_date}")
    db.commit()
    db.refresh(t)
    return serialize(t, travel.get_rates(db))


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
    data = payload.model_dump(exclude_unset=True)
    clear = data.pop("clear_override", False)
    for key, value in data.items():
        setattr(t, key, value)
    if clear:
        t.per_diem_override = None
    audit.record(db, user, "update", "travel", t.id, f"{t.traveller_name} {t.trip_date}")
    db.commit()
    db.refresh(t)
    return serialize(t, travel.get_rates(db))


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
    """Generate the two-sheet xlsx (Cestovný príkaz + VPC) for one person+month."""
    period = get_period(db, period_id)
    travels = db.scalars(
        select(Travel).where(Travel.period_id == period_id, Travel.traveller_name == name)
    ).all()
    if not travels:
        raise HTTPException(status_code=404, detail="No trips for that person in this month")
    address = next((t.traveller_address for t in travels if t.traveller_address), "")
    rates = travel.get_rates(db)
    data = travel.build_xlsx(name, address, period.year, period.month, travels, rates)

    month_name = travel._SK_MONTHS.get(period.month, str(period.month))
    fname = _ascii(f"Cestovne_{month_name}_{period.year}_{name}") + ".xlsx"
    return Response(
        content=data,
        media_type=_XLSX_MIME,
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
