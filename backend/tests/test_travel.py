"""Travel report: per-diem bands, CRUD, and xlsx export."""
import io
from datetime import date, time
from decimal import Decimal

import openpyxl

from app import travel as tv

R = tv.DEFAULT_RATES
D = date(2026, 7, 1)


def test_per_diem_bands():
    assert tv.computed_per_diem(D, time(9, 0), None, time(13, 0), R) == Decimal("0.00")     # 4h
    assert tv.computed_per_diem(D, time(7, 30), None, time(15, 30), R) == Decimal("8.80")   # 8h
    assert tv.computed_per_diem(D, time(7, 30), None, time(20, 30), R) == Decimal("13.10")  # 13h
    assert tv.computed_per_diem(D, time(7, 0), None, time(6, 0), R) == Decimal("19.50")     # 23h overnight
    assert tv.computed_per_diem(D, None, None, None, R) == Decimal("0.00")
    # Multi-day: 1 Jul 08:00 -> 2 Jul 18:00 = 34h => 1 full day (19.50) + 10h (8.80).
    assert tv.computed_per_diem(D, time(8, 0), date(2026, 7, 2), time(18, 0), R) == Decimal("28.30")


def _period(client, auth_headers, year=2026, month=7):
    return client.post("/api/periods", json={"year": year, "month": month}, headers=auth_headers).json()["id"]


def _trip(client, auth_headers, pid, **over):
    body = {
        "traveller_name": "Nikoleta", "traveller_address": "Nitra",
        "trip_date": "2026-07-01", "from_place": "Nitra", "to_place": "Trnava",
        "purpose": "Konzultácia", "depart_time": "07:30", "arrive_time": "08:15",
        "return_depart_time": "14:45", "return_arrive_time": "15:30", "transport": "Auto služobné",
    }
    body.update(over)
    return client.post(f"/api/periods/{pid}/travels", json=body, headers=auth_headers)


def test_create_list_and_per_diem(client, auth_headers):
    pid = _period(client, auth_headers)
    res = _trip(client, auth_headers, pid)
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["per_diem"] == 8.8 and body["per_diem_computed"] == 8.8
    assert body["duration_hours"] == 8.0

    lst = client.get(f"/api/periods/{pid}/travels", headers=auth_headers).json()
    assert len(lst) == 1
    names = client.get(f"/api/periods/{pid}/travel-names", headers=auth_headers).json()
    assert names == ["Nikoleta"]


def test_override_and_clear(client, auth_headers):
    pid = _period(client, auth_headers, month=8)
    tid = _trip(client, auth_headers, pid).json()["id"]
    upd = client.patch(f"/api/travels/{tid}", json={"per_diem_override": "20.00"}, headers=auth_headers).json()
    assert upd["per_diem"] == 20.0 and upd["per_diem_computed"] == 8.8
    cleared = client.patch(f"/api/travels/{tid}", json={"clear_override": True}, headers=auth_headers).json()
    assert cleared["per_diem"] == 8.8


def test_delete_trip(client, auth_headers):
    pid = _period(client, auth_headers, month=9)
    tid = _trip(client, auth_headers, pid).json()["id"]
    assert client.delete(f"/api/travels/{tid}", headers=auth_headers).status_code == 204
    assert client.get(f"/api/periods/{pid}/travels", headers=auth_headers).json() == []


def test_per_diem_rates_get_set(client, auth_headers):
    got = client.get("/api/travel/per-diem-rates", headers=auth_headers).json()
    assert got == {"band1": 8.8, "band2": 13.1, "band3": 19.5}
    client.patch("/api/travel/per-diem-rates", json={"band1": 9.0, "band2": 14.0, "band3": 21.0}, headers=auth_headers)
    # New rate flows into computed per-diem.
    pid = _period(client, auth_headers, month=10)
    body = _trip(client, auth_headers, pid).json()
    assert body["per_diem"] == 9.0


def test_export_xlsx(client, auth_headers):
    pid = _period(client, auth_headers, month=11)
    _trip(client, auth_headers, pid)
    _trip(client, auth_headers, pid, trip_date="2026-11-02", depart_time="07:00",
          return_arrive_time="21:00")  # 14h -> band2 13.10

    res = client.get(f"/api/periods/{pid}/travels/export", params={"name": "Nikoleta"}, headers=auth_headers)
    assert res.status_code == 200, res.text
    assert "spreadsheetml" in res.headers["content-type"]

    wb = openpyxl.load_workbook(io.BytesIO(res.content))
    assert wb.sheetnames == ["November", "VPC"]
    s1 = wb["November"]
    assert s1["B2"].value == "CESTOVNÝ PRÍKAZ"
    assert s1["C4"].value == "Nikoleta"
    # VPC totals: 8.80 + 13.10 = 21.90
    vpc = wb["VPC"]
    spolu = [c.value for row in vpc.iter_rows() for c in row if c.value == "SPOLU"]
    assert spolu, "SPOLU row present"
    total_cells = [c.value for row in vpc.iter_rows() for c in row
                   if isinstance(c.value, (int, float)) and abs(c.value - 21.90) < 0.001]
    assert total_cells, "total 21.90 present"


def test_multiday_trip(client, auth_headers):
    pid = _period(client, auth_headers, month=3)
    res = _trip(client, auth_headers, pid, trip_date="2026-03-01", end_date="2026-03-02",
                depart_time="08:00", return_arrive_time="18:00")
    body = res.json()
    assert body["end_date"] == "2026-03-02"
    assert body["per_diem"] == 28.3  # 34h -> 19.50 + 8.80


def test_duplicate_trip(client, auth_headers):
    pid = _period(client, auth_headers, month=4)
    tid = _trip(client, auth_headers, pid).json()["id"]
    dup = client.post(f"/api/travels/{tid}/duplicate", headers=auth_headers)
    assert dup.status_code == 201, dup.text
    assert dup.json()["id"] != tid
    assert len(client.get(f"/api/periods/{pid}/travels", headers=auth_headers).json()) == 2


def test_bulk_create_trips(client, auth_headers):
    pid = _period(client, auth_headers, month=5)
    body = {
        "traveller_name": "Bulk Person", "traveller_address": "Nitra",
        "trip_date": "2026-05-05", "from_place": "Nitra", "to_place": "Trnava",
        "purpose": "Konzultácia", "depart_time": "07:30", "arrive_time": "08:15",
        "return_depart_time": "14:45", "return_arrive_time": "15:30", "transport": "Vlak",
        "dates": ["2026-05-05", "2026-05-12", "2026-05-19"],
    }
    res = client.post(f"/api/periods/{pid}/travels/bulk", json=body, headers=auth_headers)
    assert res.status_code == 201, res.text
    created = res.json()
    assert len(created) == 3
    assert sorted(t["trip_date"] for t in created) == ["2026-05-05", "2026-05-12", "2026-05-19"]
    assert all(t["per_diem"] == 8.8 for t in created)


def test_period_with_trips_cannot_be_deleted(client, auth_headers):
    pid = _period(client, auth_headers, month=6)
    _trip(client, auth_headers, pid)
    res = client.delete(f"/api/periods/{pid}", headers=auth_headers)
    assert res.status_code == 409  # must clear trips first (no FK 500)


def test_export_missing_person_404(client, auth_headers):
    pid = _period(client, auth_headers, month=12)
    res = client.get(f"/api/periods/{pid}/travels/export", params={"name": "Nobody"}, headers=auth_headers)
    assert res.status_code == 404
