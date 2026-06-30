import unicodedata
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from .. import logbook as lb
from ..database import get_db
from ..deps import get_current_user
from ..models import CarTrip, Vehicle
from ..schemas import (
    CarTripCreate, CarTripOut, CarTripUpdate,
    VehicleCreate, VehicleOut, VehicleUpdate,
)

router = APIRouter(prefix="/api", tags=["logbook"])
_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _serialize(trip: CarTrip, vehicle: Vehicle) -> CarTripOut:
    return CarTripOut(
        id=trip.id,
        vehicle_id=trip.vehicle_id,
        journey_number=trip.journey_number,
        start_dt=trip.start_dt,
        end_dt=trip.end_dt,
        purpose=trip.purpose,
        route=trip.route,
        odometer_start=trip.odometer_start,
        odometer_end=trip.odometer_end,
        km=lb.trip_km(trip),
        driver_name=trip.driver_name,
        trip_type=trip.trip_type,
        events=trip.events,
        fuel_price_override=float(trip.fuel_price_override) if trip.fuel_price_override is not None else None,
        cost=lb.trip_cost(trip, vehicle),
        travel_id=trip.travel_id,
        created_at=trip.created_at,
    )


def _month_range(year: int, month: int) -> tuple[datetime, datetime]:
    start = datetime(year, month, 1)
    end = datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)
    return start, end


def _next_journey_number(db: Session, vehicle_id: int, year: int, month: int) -> int:
    base = year * 100000 + month * 1000
    max_num = db.scalar(
        select(func.max(CarTrip.journey_number)).where(
            CarTrip.vehicle_id == vehicle_id,
            CarTrip.journey_number >= base,
            CarTrip.journey_number < base + 1000,
        )
    )
    return (max_num or base) + 1


# ---- Vehicles ----

@router.get("/vehicles", response_model=list[VehicleOut])
def list_vehicles(db: Session = Depends(get_db), user=Depends(get_current_user)):
    vehicles = db.scalars(select(Vehicle).order_by(Vehicle.ecv)).all()
    year_start = datetime(datetime.now().year, 1, 1)
    km_diff = CarTrip.odometer_end - CarTrip.odometer_start
    stats = {
        row.vehicle_id: row
        for row in db.execute(
            select(
                CarTrip.vehicle_id,
                func.sum(km_diff).label("km_total"),
                func.sum(case((CarTrip.start_dt >= year_start, km_diff), else_=0)).label("km_ytd"),
            )
            .where(CarTrip.odometer_start.isnot(None), CarTrip.odometer_end.isnot(None))
            .group_by(CarTrip.vehicle_id)
        ).all()
    }
    result = []
    for v in vehicles:
        out = VehicleOut.model_validate(v)
        s = stats.get(v.id)
        out.km_total = int(s.km_total) if s and s.km_total is not None else None
        out.km_ytd = int(s.km_ytd) if s and s.km_ytd else None
        result.append(out)
    return result


@router.post("/vehicles", response_model=VehicleOut, status_code=201)
def create_vehicle(
    payload: VehicleCreate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    v = Vehicle(**payload.model_dump())
    db.add(v)
    db.commit()
    db.refresh(v)
    return v


@router.patch("/vehicles/{vid}", response_model=VehicleOut)
def update_vehicle(
    vid: int,
    payload: VehicleUpdate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    v = db.get(Vehicle, vid)
    if not v:
        raise HTTPException(404, "Vehicle not found")
    for k, val in payload.model_dump(exclude_unset=True).items():
        setattr(v, k, val)
    db.commit()
    db.refresh(v)
    return v


@router.delete("/vehicles/{vid}", status_code=204)
def delete_vehicle(
    vid: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    v = db.get(Vehicle, vid)
    if not v:
        raise HTTPException(404, "Vehicle not found")
    count = db.scalar(select(func.count()).where(CarTrip.vehicle_id == vid))
    if count:
        raise HTTPException(409, f"Vehicle has {count} trip(s) — delete trips first")
    db.delete(v)
    db.commit()


# ---- Car trips ----

@router.get("/vehicles/{vid}/trips", response_model=list[CarTripOut])
def list_trips(
    vid: int,
    year: int = Query(...),
    month: int = Query(...),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    v = db.get(Vehicle, vid)
    if not v:
        raise HTTPException(404, "Vehicle not found")
    start, end = _month_range(year, month)
    trips = db.scalars(
        select(CarTrip).where(
            CarTrip.vehicle_id == vid,
            CarTrip.start_dt >= start,
            CarTrip.start_dt < end,
        ).order_by(CarTrip.start_dt)
    ).all()
    return [_serialize(t, v) for t in trips]


@router.get("/vehicles/{vid}/trip-months")
def trip_months(
    vid: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    rows = db.scalars(
        select(CarTrip.start_dt).where(CarTrip.vehicle_id == vid)
    ).all()
    seen: set[tuple[int, int]] = set()
    result = []
    for dt in sorted(rows):
        key = (dt.year, dt.month)
        if key not in seen:
            seen.add(key)
            result.append({"year": dt.year, "month": dt.month})
    return result


@router.post("/vehicles/{vid}/trips", response_model=CarTripOut, status_code=201)
def create_trip(
    vid: int,
    payload: CarTripCreate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    v = db.get(Vehicle, vid)
    if not v:
        raise HTTPException(404, "Vehicle not found")
    jnum = _next_journey_number(db, vid, payload.start_dt.year, payload.start_dt.month)
    t = CarTrip(vehicle_id=vid, journey_number=jnum, **payload.model_dump())
    db.add(t)
    db.commit()
    db.refresh(t)
    return _serialize(t, v)


@router.patch("/car-trips/{tid}", response_model=CarTripOut)
def update_trip(
    tid: int,
    payload: CarTripUpdate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    t = db.get(CarTrip, tid)
    if not t:
        raise HTTPException(404, "Trip not found")
    v = db.get(Vehicle, t.vehicle_id)
    for k, val in payload.model_dump(exclude_unset=True).items():
        setattr(t, k, val)
    db.commit()
    db.refresh(t)
    return _serialize(t, v)


@router.delete("/car-trips/{tid}", status_code=204)
def delete_trip(
    tid: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    t = db.get(CarTrip, tid)
    if not t:
        raise HTTPException(404, "Trip not found")
    db.delete(t)
    db.commit()


@router.post("/vehicles/{vid}/trips/import")
async def import_trips(
    vid: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    v = db.get(Vehicle, vid)
    if not v:
        raise HTTPException(404, "Vehicle not found")
    data = await file.read()
    try:
        rows = lb.parse_xlsx(data)
    except Exception as e:
        raise HTTPException(400, f"Could not parse xlsx: {e}")

    imported = 0
    skipped = 0
    errors: list[str] = []
    for i, row in enumerate(rows, 1):
        if not row.get("start_dt"):
            skipped += 1
            errors.append(f"Row {i}: missing start date")
            continue
        jnum = _next_journey_number(db, vid, row["start_dt"].year, row["start_dt"].month)
        t = CarTrip(vehicle_id=vid, journey_number=jnum, **row)
        db.add(t)
        db.flush()
        imported += 1
    db.commit()
    return {"imported": imported, "skipped": skipped, "errors": errors}


@router.get("/vehicles/{vid}/trips/export")
def export_trips(
    vid: int,
    year: int = Query(...),
    month: int = Query(...),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    v = db.get(Vehicle, vid)
    if not v:
        raise HTTPException(404, "Vehicle not found")
    start, end = _month_range(year, month)
    trips = db.scalars(
        select(CarTrip).where(
            CarTrip.vehicle_id == vid,
            CarTrip.start_dt >= start,
            CarTrip.start_dt < end,
        ).order_by(CarTrip.start_dt)
    ).all()
    if not trips:
        raise HTTPException(404, "No trips for that vehicle in this month")
    data = lb.build_xlsx(v, list(trips))

    def _ascii(s: str) -> str:
        d = unicodedata.normalize("NFKD", s)
        out = "".join(c for c in d if not unicodedata.combining(c) and ord(c) < 128)
        return "".join(c if c.isalnum() else "_" for c in out).strip("_") or "logbook"

    fname = _ascii(f"Kniha_jazd_{v.ecv}_{year}_{month:02d}") + ".xlsx"
    return Response(
        content=data,
        media_type=_XLSX_MIME,
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
