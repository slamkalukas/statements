import json
import os
import re
import unicodedata
from datetime import datetime
from functools import lru_cache

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel, Field, field_validator
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
_NOMINATIM = "https://nominatim.openstreetmap.org/search"
_OSRM = "http://router.project-osrm.org/route/v1/driving"


def _parse_waypoints(route: str) -> list[str]:
    parts = re.split(r"\s*[>→]\s*|\s+-\s+", route.strip())
    return [p.strip() for p in parts if p.strip()]


@lru_cache(maxsize=512)
def _geocode(city: str) -> tuple[float, float] | None:
    """City coordinates rarely change, and the same waypoints get re-typed
    across trips — cache to stay within Nominatim's ~1 req/sec usage policy."""
    try:
        r = httpx.get(
            _NOMINATIM,
            params={"q": city, "format": "json", "limit": 1},
            headers={"User-Agent": "statements-app/1.0"},
            timeout=5.0,
        )
        data = r.json()
        if data:
            return float(data[0]["lon"]), float(data[0]["lat"])
    except Exception:
        pass
    return None


def _driving_km(coords: list[tuple[float, float]]) -> float:
    waypoints = ";".join(f"{lon},{lat}" for lon, lat in coords)
    r = httpx.get(f"{_OSRM}/{waypoints}", params={"overview": "false"}, timeout=10.0)
    data = r.json()
    if data.get("code") != "Ok":
        raise ValueError(data.get("message", "Routing failed"))
    return data["routes"][0]["distance"] / 1000


class _RouteIn(BaseModel):
    route: str


def _serialize(trip: CarTrip, vehicle: Vehicle) -> CarTripOut:
    return CarTripOut(
        id=trip.id,
        vehicle_id=trip.vehicle_id,
        journey_number=trip.journey_number,
        start_dt=trip.start_dt,
        end_dt=trip.end_dt,
        purpose=trip.purpose,
        route=trip.route,
        km=trip.km,
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


# ---- Route distance ----

@router.post("/route-distance")
def route_distance(payload: _RouteIn, user=Depends(get_current_user)):
    cities = _parse_waypoints(payload.route)
    if len(cities) < 2:
        raise HTTPException(400, "Need at least 2 waypoints — separate cities with >")
    coords: list[tuple[float, float]] = []
    for city in cities:
        c = _geocode(city)
        if c is None:
            raise HTTPException(400, f"Could not find location: {city}")
        coords.append(c)
    try:
        km = _driving_km(coords)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"km": round(km)}


# ---- AI trip suggestion ----

class _AiTripIn(BaseModel):
    description: str = Field(max_length=500)
    home_city: str = Field(default="", max_length=120)
    date: str = Field(default="", max_length=10)  # YYYY-MM-DD


class _AiTripSuggestion(BaseModel):
    """The AI's free-form JSON, coerced into a shape the frontend can trust.

    Individual bad fields (an odd time format, a non-numeric km, an unknown
    trip_type) are nulled/defaulted rather than failing the whole request —
    a partially-usable suggestion beats losing the feature over one bad field.
    """
    purpose: str = ""
    route: str = ""
    km: int | None = None
    start_time: str | None = None
    end_time: str | None = None
    trip_type: str = "Firemná"

    @field_validator("purpose", "route", mode="before")
    @classmethod
    def _coerce_str(cls, v):
        return v if isinstance(v, str) else ""

    @field_validator("km", mode="before")
    @classmethod
    def _coerce_km(cls, v):
        if v in (None, ""):
            return None
        try:
            return int(round(float(v)))
        except (TypeError, ValueError):
            return None

    @field_validator("start_time", "end_time", mode="before")
    @classmethod
    def _coerce_time(cls, v):
        return v if isinstance(v, str) and re.fullmatch(r"\d{2}:\d{2}", v) else None

    @field_validator("trip_type", mode="before")
    @classmethod
    def _coerce_trip_type(cls, v):
        return v if v in ("Firemná", "Súkromná") else "Firemná"


_AI_PROMPT = """\
You are a Slovak company vehicle logbook assistant. Given a short trip description, \
return ONLY a valid JSON object — no extra text, no markdown fences — with these fields:
- "purpose": trip purpose in Slovak (e.g. "Nákup tovaru", "Stretnutie s klientom")
- "route": route like "CityA > CityB > CityA" for round trips; include country code if outside Slovakia
- "km": estimated total km as an integer (round trip), or null if you cannot estimate
- "start_time": suggested departure as "HH:MM", or null
- "end_time": suggested return as "HH:MM", or null
- "trip_type": "Firemná" or "Súkromná"

Home city: {home_city}
Date: {date}
Description: {description}"""


def _ai_generate(prompt: str) -> str:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(503, "ANTHROPIC_API_KEY not configured on the server")
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text.strip()
    except Exception as e:
        import anthropic as _a
        detail = str(e)
        if isinstance(e, _a.APIStatusError) and e.body:
            detail = (e.body.get("error") or {}).get("message") or detail
        raise HTTPException(502, f"AI error: {detail}")


@router.post("/ai-trip-suggest", response_model=_AiTripSuggestion)
def ai_trip_suggest(
    payload: _AiTripIn,
    user=Depends(get_current_user),
):
    prompt = _AI_PROMPT.format(
        home_city=payload.home_city or "unknown",
        date=payload.date or "not specified",
        description=payload.description,
    )
    text = _ai_generate(prompt)
    if "```" in text:
        text = re.sub(r"```[a-z]*", "", text).replace("```", "").strip()
    try:
        raw = json.loads(text)
    except json.JSONDecodeError:
        raise HTTPException(500, f"AI returned unparseable response: {text[:300]}")
    if not isinstance(raw, dict):
        raise HTTPException(500, f"AI returned unparseable response: {text[:300]}")
    return _AiTripSuggestion.model_validate(raw)


# ---- Place autocomplete ----

@lru_cache(maxsize=512)
def _suggest_places_cached(q: str) -> tuple[str, ...]:
    """Autocomplete fires on every keystroke — cache repeated queries so we
    don't hammer Nominatim's public (~1 req/sec) endpoint."""
    try:
        r = httpx.get(
            _NOMINATIM,
            params={"q": q, "format": "json", "limit": 7, "addressdetails": 1},
            headers={"User-Agent": "statements-app/1.0"},
            timeout=5.0,
        )
        results = r.json()
    except Exception:
        return ()

    seen: set[str] = set()
    out: list[str] = []
    for item in results:
        addr = item.get("address", {})
        city = (
            addr.get("city") or addr.get("town") or addr.get("village")
            or addr.get("municipality") or item["display_name"].split(",")[0].strip()
        )
        country = addr.get("country", "")
        label = f"{city}, {country}" if country else city
        if label not in seen:
            seen.add(label)
            out.append(label)
        if len(out) == 5:
            break
    return tuple(out)


@router.get("/suggest-places")
def suggest_places(q: str = Query(..., min_length=2), user=Depends(get_current_user)):
    return list(_suggest_places_cached(q))


# ---- Vehicles ----

@router.get("/vehicles", response_model=list[VehicleOut])
def list_vehicles(db: Session = Depends(get_db), user=Depends(get_current_user)):
    vehicles = db.scalars(select(Vehicle).order_by(Vehicle.ecv)).all()
    year_start = datetime(datetime.now().year, 1, 1)
    stats = {
        row.vehicle_id: row
        for row in db.execute(
            select(
                CarTrip.vehicle_id,
                func.sum(CarTrip.km).label("km_total"),
                func.sum(case((CarTrip.start_dt >= year_start, CarTrip.km), else_=0)).label("km_ytd"),
            )
            .where(CarTrip.km.isnot(None))
            .group_by(CarTrip.vehicle_id)
        ).all()
    }
    result = []
    for v in vehicles:
        out = VehicleOut.model_validate(v)
        s = stats.get(v.id)
        base = v.odometer_base or 0
        trip_km = int(s.km_total) if s and s.km_total is not None else 0
        total = base + trip_km
        out.km_total = total if total > 0 else None
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
    jnum = lb.next_journey_number(db, vid, payload.start_dt.year, payload.start_dt.month)
    t = CarTrip(vehicle_id=vid, journey_number=jnum, **payload.model_dump())
    db.add(t)
    db.flush()
    lb.renumber_month(db, vid, payload.start_dt.year, payload.start_dt.month)
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
    old_year, old_month = t.start_dt.year, t.start_dt.month
    for k, val in payload.model_dump(exclude_unset=True).items():
        setattr(t, k, val)
    db.flush()
    lb.renumber_month(db, t.vehicle_id, old_year, old_month)
    new_year, new_month = t.start_dt.year, t.start_dt.month
    if (new_year, new_month) != (old_year, old_month):
        lb.renumber_month(db, t.vehicle_id, new_year, new_month)
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
    vid = t.vehicle_id
    jnum = t.journey_number
    year = jnum // 100000
    month = (jnum % 100000) // 1000
    db.delete(t)
    db.flush()
    lb.renumber_month(db, vid, year, month)
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
    touched_months: set[tuple[int, int]] = set()
    try:
        for i, row in enumerate(rows, 1):
            if not row.get("start_dt"):
                skipped += 1
                errors.append(f"Row {i}: missing start date")
                continue
            year, month = row["start_dt"].year, row["start_dt"].month
            jnum = lb.next_journey_number(db, vid, year, month)
            t = CarTrip(vehicle_id=vid, journey_number=jnum, **row)
            db.add(t)
            db.flush()
            touched_months.add((year, month))
            imported += 1
        # Rows may arrive out of date order — renumber each affected month
        # chronologically rather than by insertion order.
        for year, month in touched_months:
            lb.renumber_month(db, vid, year, month)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(400, f"Import failed on row {imported + skipped + 1}: {e}")
    return {"imported": imported, "skipped": skipped, "errors": errors}


@router.get("/vehicles/{vid}/trips/export")
def export_trips(
    vid: int,
    year: int = Query(None),
    month: int = Query(None),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    v = db.get(Vehicle, vid)
    if not v:
        raise HTTPException(404, "Vehicle not found")
    if year and month:
        start, end = _month_range(year, month)
        q = select(CarTrip).where(
            CarTrip.vehicle_id == vid,
            CarTrip.start_dt >= start,
            CarTrip.start_dt < end,
        )
        prior_km = db.scalar(
            select(func.sum(CarTrip.km))
            .where(CarTrip.vehicle_id == vid, CarTrip.start_dt < start, CarTrip.km.isnot(None))
        ) or 0
        base_odometer = (v.odometer_base or 0) + int(prior_km)
    else:
        q = select(CarTrip).where(CarTrip.vehicle_id == vid)
        base_odometer = v.odometer_base or 0
    trips = db.scalars(q.order_by(CarTrip.start_dt)).all()
    if not trips:
        raise HTTPException(404, "No trips recorded for this vehicle")
    data = lb.build_xlsx(v, list(trips), base_odometer)

    def _ascii(s: str) -> str:
        d = unicodedata.normalize("NFKD", s)
        out = "".join(c for c in d if not unicodedata.combining(c) and ord(c) < 128)
        return "".join(c if c.isalnum() else "_" for c in out).strip("_") or "logbook"

    suffix = f"_{year}_{month:02d}" if year and month else ""
    fname = _ascii(f"Kniha_jazd_{v.ecv}{suffix}") + ".xlsx"
    return Response(
        content=data,
        media_type=_XLSX_MIME,
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
