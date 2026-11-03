"""Geocoding: OSM is asked first, ORS only fills in what OSM cannot place.

ORS answers every query with its best guess, which used to be written onto the
leg as a confident-looking distance (a Nitra street address landed 29 km away).
"""
import httpx
import pytest

from app import routing


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        pass


@pytest.fixture(autouse=True)
def _clear_cache():
    routing.geocode_osm.cache_clear()
    yield
    routing.geocode_osm.cache_clear()


def _fake_get(monkeypatch, osm_payload, ors_payload):
    calls = []

    def get(url, **kwargs):
        calls.append(url)
        return _Resp(osm_payload if url == routing._NOMINATIM else ors_payload)

    monkeypatch.setattr(httpx, "get", get)
    return calls


def test_osm_hit_does_not_consult_ors(monkeypatch):
    osm = [{"lon": "18.0764", "lat": "48.3062"}]
    ors = {"features": [{"geometry": {"coordinates": [0.0, 0.0]}}]}  # the bad guess
    calls = _fake_get(monkeypatch, osm, ors)

    assert routing._geocode("Nitra, Slovensko", "key") == (18.0764, 48.3062)
    assert calls == [routing._NOMINATIM]


def test_ors_fills_in_what_osm_cannot_place(monkeypatch):
    # OSM has no entry for the "Firm (street, city)" form the user types.
    ors = {"features": [{"geometry": {"coordinates": [16.3875, 48.2167]}}]}
    calls = _fake_get(monkeypatch, [], ors)

    assert routing._geocode("UNIQA Tower (Untere Donaustrasse 21, Wien)", "key") == (16.3875, 48.2167)
    assert len(calls) == 2 and calls[1].startswith(routing._BASE)


def test_unknown_place_leaves_the_leg_alone(monkeypatch):
    _fake_get(monkeypatch, [], {"features": []})
    assert routing._geocode("nowhere at all", "key") is None


def test_geocode_is_cached(monkeypatch):
    calls = _fake_get(monkeypatch, [{"lon": "1.0", "lat": "2.0"}], {})
    routing._geocode("Nitra", "key")
    routing._geocode("Nitra", "key")
    assert len(calls) == 1  # Nominatim allows ~1 req/sec
