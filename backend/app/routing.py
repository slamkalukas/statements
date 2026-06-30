"""OpenRouteService routing: geocode place names, get driving distance + duration.

Used to auto-fill distance_km and duration_min on Travel records. Everything is
best-effort: if the API key is missing, the place is ambiguous, or the service
is unreachable, we return None and the fields stay empty — the user can fill them
manually or recalculate later.
"""
import logging
from functools import lru_cache

import httpx

from .models import Setting

logger = logging.getLogger(__name__)

ORS_KEY = "ors_api_key"
_BASE = "https://api.openrouteservice.org"


def get_api_key(db) -> str | None:
    row = db.query(Setting).filter(Setting.key == ORS_KEY).first()
    return row.value.strip() if (row and row.value and row.value.strip()) else None


def set_api_key(db, key: str) -> None:
    row = db.query(Setting).filter(Setting.key == ORS_KEY).first()
    if row:
        row.value = key.strip()
    else:
        db.add(Setting(key=ORS_KEY, value=key.strip()))


def _round20(minutes: float) -> int:
    """Round to the nearest 20 minutes."""
    return round(minutes / 20) * 20


def _geocode(place: str, api_key: str) -> tuple[float, float] | None:
    """Return (lng, lat) for the first geocode result, or None."""
    try:
        r = httpx.get(
            f"{_BASE}/geocode/search",
            params={"api_key": api_key, "text": place, "size": 1},
            timeout=8,
        )
        r.raise_for_status()
        features = r.json().get("features", [])
        if not features:
            logger.warning("ORS geocode: no result for %r", place)
            return None
        coords = features[0]["geometry"]["coordinates"]  # [lng, lat]
        return (coords[0], coords[1])
    except Exception as exc:
        logger.warning("ORS geocode error for %r: %s", place, exc)
        return None


def route(from_place: str, to_place: str, api_key: str) -> tuple[float, int] | None:
    """Return (one_way_km, one_way_duration_rounded_20min), or None on failure."""
    src = _geocode(from_place, api_key)
    dst = _geocode(to_place, api_key)
    if src is None or dst is None:
        return None
    try:
        r = httpx.post(
            f"{_BASE}/v2/directions/driving-car/json",
            headers={"Authorization": api_key, "Content-Type": "application/json"},
            json={"coordinates": [list(src), list(dst)]},
            timeout=10,
        )
        r.raise_for_status()
        seg = r.json()["routes"][0]["summary"]
        km = round(seg["distance"] / 1000, 2)
        mins = _round20(seg["duration"] / 60)
        return (km, mins)
    except Exception as exc:
        logger.warning("ORS directions error %r -> %r: %s", from_place, to_place, exc)
        return None


def auto_route(db, t) -> bool:
    """Fill distance_km and duration_min on a Travel record if both places are set
    and an API key is configured. Returns True if the record was updated."""
    if not t.from_place or not t.to_place:
        return False
    api_key = get_api_key(db)
    if not api_key:
        return False
    result = route(t.from_place, t.to_place, api_key)
    if result is None:
        return False
    t.distance_km, t.duration_min = result
    return True
