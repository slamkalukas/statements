"""Travel report: per-diem bands, CRUD, and xlsx export."""
import io
import zipfile
from datetime import date, time
from decimal import Decimal

import openpyxl

from app import travel as tv

R = tv.DEFAULT_RATES
D = date(2026, 7, 1)


def test_per_diem_bands():
    # New signature: computed_per_diem(date_from, date_to, first_depart, last_arrive, rates)
    assert tv.computed_per_diem(D, None, time(9, 0), time(13, 0), R) == Decimal("0.00")    # 4h
    assert tv.computed_per_diem(D, None, time(7, 30), time(15, 30), R) == Decimal("8.80")  # 8h
    assert tv.computed_per_diem(D, None, time(7, 30), time(20, 30), R) == Decimal("13.10") # 13h
    assert tv.computed_per_diem(D, None, time(7, 0), time(6, 0), R) == Decimal("19.50")    # 23h overnight
    assert tv.computed_per_diem(D, None, None, None, R) == Decimal("0.00")
    # Multi-day: 1 Jul 08:00 -> 2 Jul 18:00 = 34h => 1 full day (19.50) + 10h (8.80).
    assert tv.computed_per_diem(D, date(2026, 7, 2), time(8, 0), time(18, 0), R) == Decimal("28.30")


def test_foreign_day_fraction_bands():
    # Share of the daily rate by hours abroad in a calendar day.
    assert tv._foreign_fraction(5) == Decimal("0.25")
    assert tv._foreign_fraction(6) == Decimal("0.25")   # boundary is inclusive
    assert tv._foreign_fraction(7) == Decimal("0.50")
    assert tv._foreign_fraction(12) == Decimal("0.50")  # boundary is inclusive
    assert tv._foreign_fraction(13) == Decimal("1")


def test_rate_book_resolves_by_date():
    book = tv.RateBook(
        domestic_history=[
            {"valid_from": date(2026, 1, 1), "band1": 8.80, "band2": 13.10, "band3": 19.50},
            {"valid_from": date(2026, 7, 1), "band1": 9.30, "band2": 14.00, "band3": 20.80},
        ],
        foreign_rates=[
            {"code": "IT", "name": "Taliansko", "rate": 45.0, "valid_from": tv.BEGINNING},
            {"code": "IT", "name": "Taliansko", "rate": 47.0, "valid_from": date(2026, 7, 1)},
        ],
    )
    # A trip keeps the rate that was in force on its own date.
    assert book.domestic(date(2026, 6, 30))["band1"] == 8.80
    assert book.domestic(date(2026, 7, 1))["band1"] == 9.30
    assert book.foreign("IT", date(2026, 6, 30)) == 45.0
    assert book.foreign("IT", date(2026, 7, 1)) == 47.0
    # Before any row, and for countries that were never configured.
    assert book.foreign("IT", date(2020, 1, 1)) == 45.0   # open-ended first row
    assert book.foreign("XX", date(2026, 7, 1)) == 0.0


def _period(client, auth_headers, year=2026, month=7):
    return client.post("/api/periods", json={"year": year, "month": month}, headers=auth_headers).json()["id"]


def _trip(client, auth_headers, pid, **over):
    body = {
        "traveller_name": "Nikoleta", "traveller_address": "Nitra",
        "trip_date": "2026-07-01", "purpose": "Konzultácia",
        "legs": [
            {"from_place": "Nitra", "to_place": "Trnava", "transport": "Auto služobné",
             "depart_time": "07:30", "arrive_time": "08:15"},
            {"from_place": "Trnava", "to_place": "Nitra", "transport": "Auto služobné",
             "depart_time": "14:45", "arrive_time": "15:30"},
        ],
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
    trip = _trip(client, auth_headers, pid).json()
    leg_id = trip["legs"][0]["id"]
    # Set per_diem on first leg — effective per_diem becomes sum of leg per_diems
    upd = client.patch(f"/api/travel-legs/{leg_id}", json={"per_diem": 20.0}, headers=auth_headers).json()
    assert upd["per_diem"] == 20.0 and upd["per_diem_computed"] == 8.8
    # Clear it — falls back to duration-based
    cleared = client.patch(f"/api/travel-legs/{leg_id}", json={"per_diem": None}, headers=auth_headers).json()
    assert cleared["per_diem"] == 8.8


def test_delete_trip(client, auth_headers):
    pid = _period(client, auth_headers, month=9)
    tid = _trip(client, auth_headers, pid).json()["id"]
    assert client.delete(f"/api/travels/{tid}", headers=auth_headers).status_code == 204
    assert client.get(f"/api/periods/{pid}/travels", headers=auth_headers).json() == []


def test_per_diem_rates_get_set(client, auth_headers):
    got = client.get("/api/travel/per-diem-rates", headers=auth_headers).json()
    assert got["rates"] == [{"valid_from": None, "band1": 8.8, "band2": 13.1, "band3": 19.5}]
    assert got["domestic_topup"] is False

    client.patch("/api/travel/per-diem-rates", headers=auth_headers, json={
        "rates": [{"valid_from": None, "band1": 9.0, "band2": 14.0, "band3": 21.0}],
    })
    # New rate flows into computed per-diem.
    pid = _period(client, auth_headers, month=10)
    body = _trip(client, auth_headers, pid).json()
    assert body["per_diem"] == 9.0


def test_domestic_rates_are_effective_dated(client, auth_headers):
    client.patch("/api/travel/per-diem-rates", headers=auth_headers, json={"rates": [
        {"valid_from": None, "band1": 8.8, "band2": 13.1, "band3": 19.5},
        {"valid_from": "2026-08-01", "band1": 9.3, "band2": 14.0, "band3": 20.8},
    ]})
    before = _period(client, auth_headers, year=2026, month=7)
    after = _period(client, auth_headers, year=2026, month=8)

    old_trip = _trip(client, auth_headers, before, trip_date="2026-07-01").json()
    new_trip = _trip(client, auth_headers, after, trip_date="2026-08-05").json()
    # Re-rating from August must not rewrite what July's trip reports.
    assert old_trip["per_diem"] == 8.8
    assert new_trip["per_diem"] == 9.3


def test_export_xlsx(client, auth_headers):
    pid = _period(client, auth_headers, month=11)
    _trip(client, auth_headers, pid)
    # Second trip: 14h → band2 → 13.10
    _trip(client, auth_headers, pid, trip_date="2026-11-02", legs=[
        {"from_place": "Nitra", "to_place": "Trnava", "transport": "Auto služobné",
         "depart_time": "07:00", "arrive_time": "08:00"},
        {"from_place": "Trnava", "to_place": "Nitra", "transport": "Auto služobné",
         "depart_time": "20:00", "arrive_time": "21:00"},
    ])

    res = client.get(f"/api/periods/{pid}/travels/export", params={"name": "Nikoleta"}, headers=auth_headers)
    assert res.status_code == 200, res.text
    assert "spreadsheetml" in res.headers["content-type"]

    wb = openpyxl.load_workbook(io.BytesIO(res.content))
    assert wb.sheetnames == ["November", "VPC"]
    s1 = wb["November"]
    assert s1["B2"].value == "CESTOVNÝ PRÍKAZ"
    assert s1["C4"].value == "Nikoleta"

    vpc = wb["VPC"]
    spolu = [c.value for row in vpc.iter_rows() for c in row if c.value == "SPOLU"]
    assert spolu, "SPOLU row present"
    # Stravné (column F) are raw floats; SPOLU uses a formula so we sum the raw values.
    # Each trip's last Príchod row carries its effective per_diem: 8.80 + 13.10 = 21.90
    f_vals = [c.value for row in vpc.iter_rows() for c in row
              if c.column == 6 and isinstance(c.value, (int, float))]
    assert abs(sum(f_vals) - 21.90) < 0.001, f"expected stravné total 21.90, got {f_vals}"


def test_multiday_trip(client, auth_headers):
    pid = _period(client, auth_headers, month=3)
    res = _trip(client, auth_headers, pid, trip_date="2026-03-01", end_date="2026-03-02", legs=[
        {"from_place": "Nitra", "to_place": "Trnava", "transport": "Auto služobné",
         "depart_time": "08:00", "arrive_time": "09:00"},
        {"from_place": "Trnava", "to_place": "Nitra", "transport": "Auto služobné",
         "depart_time": "17:00", "arrive_time": "18:00"},
    ])
    body = res.json()
    assert body["end_date"] == "2026-03-02"
    assert body["per_diem"] == 28.3  # 34h -> 19.50 + 8.80


def test_leg_place_accepts_long_full_address(client, auth_headers):
    # Full Nominatim POI addresses (street + district + city + postcode + country)
    # regularly exceed a tight limit — this one is 128 chars, previously capped at 120.
    long_place = (
        "Uniqa Tower, Ferdinandstraße, Czerninviertel, Leopoldstadt, "
        "Katastralgemeinde Leopoldstadt, Leopoldstadt, Wien, 1020, Österreich"
    )
    assert len(long_place) > 120
    pid = _period(client, auth_headers, month=2)
    res = _trip(client, auth_headers, pid, legs=[
        {"from_place": long_place, "to_place": "Nitra", "transport": "Auto služobné",
         "depart_time": "08:00", "arrive_time": "09:00"},
        {"from_place": "Nitra", "to_place": long_place, "transport": "Auto služobné",
         "depart_time": "17:00", "arrive_time": "18:00"},
    ])
    assert res.status_code == 201, res.text
    assert res.json()["legs"][0]["from_place"] == long_place


def _stay_trip(client, auth_headers, pid):
    """Multi-day trip: drive out, spend a day at a conference, drive back."""
    return _trip(client, auth_headers, pid, trip_date="2026-07-01", end_date="2026-07-03", legs=[
        {"from_place": "Nitra", "to_place": "Wien", "transport": "Auto služobné",
         "depart_time": "08:00", "arrive_time": "11:00"},
        {"kind": "stay", "from_place": "Wien", "to_place": "Wien",
         "note": "Konferencia IT", "leg_date": "2026-07-02", "expense": 120.0},
        {"from_place": "Wien", "to_place": "Nitra", "transport": "Auto služobné",
         "depart_time": "16:00", "arrive_time": "19:00"},
    ])


def test_stay_leg_round_trips(client, auth_headers):
    pid = _period(client, auth_headers)
    res = _stay_trip(client, auth_headers, pid)
    assert res.status_code == 201, res.text

    legs = res.json()["legs"]
    assert [l["kind"] for l in legs] == ["travel", "stay", "travel"]
    stay = legs[1]
    assert stay["note"] == "Konferencia IT"
    assert stay["leg_date"] == "2026-07-02"
    assert stay["expense"] == 120.0
    assert stay["transport"] == ""
    assert stay["distance_km"] is None  # a stay is never routed


def test_stay_leg_is_one_row_in_the_vpc_sheet(client, auth_headers):
    pid = _period(client, auth_headers)
    _stay_trip(client, auth_headers, pid)

    res = client.get(f"/api/periods/{pid}/travels/export", params={"name": "Nikoleta"}, headers=auth_headers)
    assert res.status_code == 200, res.text
    vpc = openpyxl.load_workbook(io.BytesIO(res.content))["VPC"]
    labels = [c.value for row in vpc.iter_rows() for c in row
              if c.column == 3 and isinstance(c.value, str)]

    stay_rows = [l for l in labels if l.startswith("Pobyt")]
    assert stay_rows == ["Pobyt Wien — Konferencia IT"]  # exactly one row, not a pair
    # The travel legs still render as Odchod/Príchod pairs around it.
    assert sum(l.startswith("Odchod") for l in labels) == 2
    assert sum(l.startswith("Príchod") for l in labels) == 2


def test_stay_leg_does_not_reach_the_logbook(client, auth_headers):
    vres = client.post("/api/vehicles", json={"ecv": "NR123XY"}, headers=auth_headers)
    vid = vres.json()["id"]
    pid = _period(client, auth_headers)
    _stay_trip(client, auth_headers, pid)

    trips = client.get(
        f"/api/vehicles/{vid}/trips", params={"year": 2026, "month": 7}, headers=auth_headers
    ).json()
    # One car trip from the two driving legs — the stay contributes no route/km.
    assert len(trips) == 1
    assert "Wien" in trips[0]["route"]
    assert trips[0]["route"].count("Wien") == 1


def test_foreign_rates_settings_round_trip(client, auth_headers):
    assert client.get("/api/travel/foreign-per-diem-rates", headers=auth_headers).json()["rates"] == []

    res = _set_foreign(client, auth_headers, [
        {"code": "it", "name": "Taliansko", "rate": 45},
        {"code": "AT", "name": "Rakúsko", "rate": 45.5},
        {"code": "IT", "name": "Taliansko", "rate": 47, "valid_from": "2026-10-01"},
        {"code": "IT", "name": "same date ignored", "rate": 99},
    ])
    assert res.status_code == 200, res.text
    saved = res.json()["rates"]
    # Codes upper-cased; one row per (code, valid_from) so a country keeps a
    # rate history, and rows with the same date collapse to the first.
    assert [(r["code"], r["rate"], r["valid_from"]) for r in saved] == [
        ("AT", 45.5, None),
        ("IT", 45.0, None),
        ("IT", 47.0, "2026-10-01"),
    ]
    assert client.get("/api/travel/foreign-per-diem-rates", headers=auth_headers).json()["rates"] == saved


def _rome_trip(client, auth_headers, pid, **over):
    """Fly out 1.9. landing 10:00, conference on the 2nd, fly back 3.9. 21:00."""
    body = dict(trip_date="2026-09-01", end_date="2026-09-03", legs=[
        {"from_place": "Nitra", "to_place": "Roma", "transport": "Lietadlo",
         "country": "IT", "depart_time": "08:00", "arrive_time": "10:00"},
        {"kind": "stay", "from_place": "Roma", "to_place": "Roma",
         "note": "konferencia", "leg_date": "2026-09-02"},
        {"from_place": "Roma", "to_place": "Nitra", "transport": "Lietadlo",
         "depart_time": "21:00", "arrive_time": "23:00"},
    ])
    body.update(over)
    return _trip(client, auth_headers, pid, **body)


def _set_foreign(client, auth_headers, rates):
    return client.patch("/api/travel/foreign-per-diem-rates",
                        headers=auth_headers, json={"rates": rates})


def test_foreign_trip_uses_country_rate_not_domestic_bands(client, auth_headers):
    _set_foreign(client, auth_headers, [{"code": "IT", "name": "Taliansko", "rate": 45}])
    pid = _period(client, auth_headers, year=2026, month=9)

    trip = _rome_trip(client, auth_headers, pid).json()
    assert trip["legs"][0]["country"] == "IT"
    # 3 calendar days abroad, each over 12 h -> 3 x 45. The domestic bands would
    # have given 52.10 for the same 63-hour span.
    assert trip["per_diem"] == 135.0
    assert trip["per_diem_computed"] == 135.0


def test_domestic_trip_unaffected_by_foreign_rates(client, auth_headers):
    _set_foreign(client, auth_headers, [{"code": "IT", "name": "Taliansko", "rate": 45}])
    pid = _period(client, auth_headers)
    trip = _trip(client, auth_headers, pid).json()  # no leg has a country
    assert all(l["country"] == "" for l in trip["legs"])
    assert trip["per_diem"] == 8.8


def test_foreign_trip_without_configured_rate_earns_nothing(client, auth_headers):
    pid = _period(client, auth_headers, year=2026, month=9)
    trip = _rome_trip(client, auth_headers, pid, legs=[
        {"from_place": "Nitra", "to_place": "Roma", "transport": "Lietadlo",
         "country": "XX", "depart_time": "08:00", "arrive_time": "10:00"},
        {"from_place": "Roma", "to_place": "Nitra", "transport": "Lietadlo",
         "depart_time": "21:00", "arrive_time": "23:00"},
    ]).json()
    # Better a visible zero than silently billing domestic rates for a foreign trip.
    assert trip["per_diem"] == 0.0


def test_marking_a_leg_foreign_recalculates(client, auth_headers):
    _set_foreign(client, auth_headers, [{"code": "IT", "name": "Taliansko", "rate": 45}])
    pid = _period(client, auth_headers, year=2026, month=9)
    trip = _rome_trip(client, auth_headers, pid, legs=[
        {"from_place": "Nitra", "to_place": "Roma", "transport": "Lietadlo",
         "depart_time": "08:00", "arrive_time": "10:00"},
        {"kind": "stay", "from_place": "Roma", "to_place": "Roma",
         "note": "konferencia", "leg_date": "2026-09-02"},
        {"from_place": "Roma", "to_place": "Nitra", "transport": "Lietadlo",
         "depart_time": "21:00", "arrive_time": "23:00"},
    ]).json()
    assert trip["per_diem"] == 52.1  # domestic bands while no leg has a country

    res = client.patch(f"/api/travel-legs/{trip['legs'][0]['id']}",
                       json={"country": "IT"}, headers=auth_headers)
    assert res.status_code == 200, res.text
    assert res.json()["per_diem"] == 135.0


def test_foreign_rates_are_effective_dated(client, auth_headers):
    _set_foreign(client, auth_headers, [
        {"code": "IT", "name": "Taliansko", "rate": 45, "valid_from": None},
        {"code": "IT", "name": "Taliansko", "rate": 47, "valid_from": "2026-10-01"},
    ])
    sep = _period(client, auth_headers, year=2026, month=9)
    octo = _period(client, auth_headers, year=2026, month=10)

    september = _rome_trip(client, auth_headers, sep).json()
    october = _rome_trip(client, auth_headers, octo,
                         trip_date="2026-10-01", end_date="2026-10-03",
                         legs=[
                             {"from_place": "Nitra", "to_place": "Roma", "transport": "Lietadlo",
                              "country": "IT", "depart_time": "08:00", "arrive_time": "10:00"},
                             {"from_place": "Roma", "to_place": "Nitra", "transport": "Lietadlo",
                              "depart_time": "21:00", "arrive_time": "23:00"},
                         ]).json()
    # Raising Italy from October leaves September's trip reporting the old rate.
    assert september["per_diem"] == 135.0
    assert october["per_diem"] == 141.0  # 3 x 47


def test_trip_spanning_two_countries_rates_each_day_separately(client, auth_headers):
    _set_foreign(client, auth_headers, [
        {"code": "IT", "name": "Taliansko", "rate": 45},
        {"code": "AT", "name": "Rakúsko", "rate": 60},
    ])
    pid = _period(client, auth_headers, year=2026, month=9)
    # Rome on the 1st-2nd, drive to Vienna midday on the 2nd, home on the 3rd.
    trip = _trip(client, auth_headers, pid,
                 trip_date="2026-09-01", end_date="2026-09-03", legs=[
        {"from_place": "Nitra", "to_place": "Roma", "transport": "Lietadlo",
         "country": "IT", "depart_time": "08:00", "arrive_time": "10:00"},
        {"from_place": "Roma", "to_place": "Wien", "transport": "Lietadlo",
         "country": "AT", "leg_date": "2026-09-02",
         "depart_time": "14:00", "arrive_time": "16:00"},
        {"from_place": "Wien", "to_place": "Nitra", "transport": "Auto služobné",
         "depart_time": "18:00", "arrive_time": "20:00"},
    ]).json()
    # 1.9: 14 h in IT -> 45. 2.9: 16 h IT + 8 h AT -> 24 h abroad at IT's rate
    # (most hours) -> 45. 3.9: 20 h in AT -> 60. Total 150.
    assert trip["per_diem"] == 150.0


def test_stay_can_name_its_own_country(client, auth_headers):
    _set_foreign(client, auth_headers, [
        {"code": "IT", "name": "Taliansko", "rate": 45},
        {"code": "AT", "name": "Rakusko", "rate": 60},
    ])
    pid = _period(client, auth_headers, year=2026, month=9)
    # Fly to Rome, but spend the middle day at a conference in Vienna without a
    # leg recording the hop — the stay says where it was.
    trip = _trip(client, auth_headers, pid,
                 trip_date="2026-09-01", end_date="2026-09-03", legs=[
        {"from_place": "Nitra", "to_place": "Roma", "transport": "Lietadlo",
         "country": "IT", "depart_time": "08:00", "arrive_time": "10:00"},
        {"kind": "stay", "from_place": "Wien", "to_place": "Wien", "country": "AT",
         "note": "konferencia", "leg_date": "2026-09-02"},
        {"from_place": "Roma", "to_place": "Nitra", "transport": "Lietadlo",
         "depart_time": "21:00", "arrive_time": "23:00"},
    ]).json()
    assert trip["legs"][1]["country"] == "AT"
    # 1.9: 14 h IT -> 45. From 2.9 00:00 the stay puts you in Austria, so
    # 2.9: 24 h AT -> 60, and 3.9: 23 h AT -> 60. Total 165.
    assert trip["per_diem"] == 165.0


def test_stay_without_a_country_still_inherits(client, auth_headers):
    _set_foreign(client, auth_headers, [{"code": "IT", "name": "Taliansko", "rate": 45}])
    pid = _period(client, auth_headers, year=2026, month=9)
    assert _rome_trip(client, auth_headers, pid).json()["per_diem"] == 135.0


def test_domestic_topup_pays_the_slovak_part_of_a_foreign_day(client, auth_headers):
    _set_foreign(client, auth_headers, [{"code": "IT", "name": "Taliansko", "rate": 45}])
    pid = _period(client, auth_headers, year=2026, month=9)
    # Leave at 04:00, land in Rome at 12:00 -> 8 h in Slovakia that day.
    legs = [
        {"from_place": "Nitra", "to_place": "Roma", "transport": "Lietadlo",
         "country": "IT", "depart_time": "04:00", "arrive_time": "12:00"},
        {"from_place": "Roma", "to_place": "Nitra", "transport": "Lietadlo",
         "depart_time": "21:00", "arrive_time": "23:00"},
    ]
    off = _trip(client, auth_headers, pid, trip_date="2026-09-01",
                end_date="2026-09-02", legs=legs).json()
    # 1.9: 12 h abroad -> 50 % of 45 = 22.50. 2.9: 23 h -> 45. Slovak part ignored.
    assert off["per_diem"] == 67.5

    client.patch("/api/travel/per-diem-rates", headers=auth_headers, json={
        "rates": [{"valid_from": None, "band1": 8.8, "band2": 13.1, "band3": 19.5}],
        "domestic_topup": True,
    })
    on = _trip(client, auth_headers, pid, trip_date="2026-09-01",
               end_date="2026-09-02", legs=legs).json()
    # Same days, plus 8 h in Slovakia on the 1st -> band1 8.80.
    assert on["per_diem"] == 76.3


def test_domestic_topup_needs_five_hours_of_its_own(client, auth_headers):
    _set_foreign(client, auth_headers, [{"code": "IT", "name": "Taliansko", "rate": 45}])
    client.patch("/api/travel/per-diem-rates", headers=auth_headers, json={
        "rates": [{"valid_from": None, "band1": 8.8, "band2": 13.1, "band3": 19.5}],
        "domestic_topup": True,
    })
    pid = _period(client, auth_headers, year=2026, month=9)
    # Rome trip has only 2 h in Slovakia each end — under the 5 h threshold, so
    # the top-up adds nothing and the total is unchanged.
    assert _rome_trip(client, auth_headers, pid).json()["per_diem"] == 135.0


def test_foreign_per_diem_reaches_the_xlsx(client, auth_headers):
    client.patch("/api/travel/foreign-per-diem-rates", headers=auth_headers,
                 json={"rates": [{"code": "IT", "name": "Taliansko", "rate": 45}]})
    pid = _period(client, auth_headers, year=2026, month=9)
    _rome_trip(client, auth_headers, pid)

    res = client.get(f"/api/periods/{pid}/travels/export",
                     params={"name": "Nikoleta"}, headers=auth_headers)
    assert res.status_code == 200, res.text
    vpc = openpyxl.load_workbook(io.BytesIO(res.content))["VPC"]
    amounts = [c.value for row in vpc.iter_rows() for c in row
               if c.column == 6 and isinstance(c.value, (int, float))]
    assert amounts == [135.0]


def test_duplicate_trip(client, auth_headers):
    pid = _period(client, auth_headers, month=4)
    tid = _trip(client, auth_headers, pid).json()["id"]
    dup = client.post(f"/api/travels/{tid}/duplicate", headers=auth_headers)
    assert dup.status_code == 201, dup.text
    assert dup.json()["id"] != tid
    assert len(client.get(f"/api/periods/{pid}/travels", headers=auth_headers).json()) == 2


def test_duplicate_keeps_country_and_stay_legs(client, auth_headers):
    _set_foreign(client, auth_headers, [{"code": "IT", "name": "Taliansko", "rate": 45}])
    pid = _period(client, auth_headers, year=2026, month=9)
    tid = _rome_trip(client, auth_headers, pid).json()["id"]

    dup = client.post(f"/api/travels/{tid}/duplicate", headers=auth_headers)
    assert dup.status_code == 201, dup.text
    body = dup.json()
    # A duplicate that quietly became a domestic trip, or whose stay turned into a
    # travel leg, would be worth real money on the report.
    assert body["legs"][0]["country"] == "IT"
    assert body["per_diem"] == 135.0
    assert [l["kind"] for l in body["legs"]] == ["travel", "stay", "travel"]
    assert body["legs"][1]["note"] == "konferencia"
    assert body["legs"][1]["leg_date"] == "2026-09-02"


def test_update_trip_date_moves_it_to_matching_period(client, auth_headers):
    march_pid = _period(client, auth_headers, month=3)
    april_pid = _period(client, auth_headers, month=4)
    tid = _trip(client, auth_headers, march_pid, trip_date="2026-03-15").json()["id"]

    res = client.patch(f"/api/travels/{tid}", json={"trip_date": "2026-04-10"}, headers=auth_headers)
    assert res.status_code == 200, res.text
    assert res.json()["period_id"] == april_pid

    assert client.get(f"/api/periods/{march_pid}/travels", headers=auth_headers).json() == []
    april_list = client.get(f"/api/periods/{april_pid}/travels", headers=auth_headers).json()
    assert [t["id"] for t in april_list] == [tid]


def test_update_trip_date_without_matching_period_404s_and_keeps_original(client, auth_headers):
    march_pid = _period(client, auth_headers, month=3)
    tid = _trip(client, auth_headers, march_pid, trip_date="2026-03-15").json()["id"]

    res = client.patch(f"/api/travels/{tid}", json={"trip_date": "2026-05-01"}, headers=auth_headers)
    assert res.status_code == 404
    assert "Months" in res.json()["detail"]

    unchanged = client.get(f"/api/periods/{march_pid}/travels", headers=auth_headers).json()
    assert len(unchanged) == 1 and unchanged[0]["trip_date"] == "2026-03-15"


def test_bulk_create_trips(client, auth_headers):
    pid = _period(client, auth_headers, month=5)
    body = {
        "traveller_name": "Bulk Person", "traveller_address": "Nitra",
        "trip_date": "2026-05-05", "purpose": "Konzultácia",
        "dates": ["2026-05-05", "2026-05-12", "2026-05-19"],
        "legs": [
            {"from_place": "Nitra", "to_place": "Trnava", "transport": "Vlak",
             "depart_time": "07:30", "arrive_time": "08:15"},
            {"from_place": "Trnava", "to_place": "Nitra", "transport": "Vlak",
             "depart_time": "14:45", "arrive_time": "15:30"},
        ],
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


def test_export_year_bundles_every_person_and_month(client, auth_headers):
    jan_pid = _period(client, auth_headers, year=2027, month=1)
    feb_pid = _period(client, auth_headers, year=2027, month=2)
    _trip(client, auth_headers, jan_pid, traveller_name="Nikoleta", trip_date="2027-01-05")
    _trip(client, auth_headers, jan_pid, traveller_name="Peter", trip_date="2027-01-10")
    _trip(client, auth_headers, feb_pid, traveller_name="Nikoleta", trip_date="2027-02-15")

    res = client.get("/api/travels/export-year", params={"year": 2027}, headers=auth_headers)
    assert res.status_code == 200, res.text
    assert "application/zip" in res.headers["content-type"]
    assert "Cestovne_2027.zip" in res.headers["content-disposition"]

    names = zipfile.ZipFile(io.BytesIO(res.content)).namelist()
    assert len(names) == 3  # Nikoleta x2 months + Peter x1 month
    assert all(n.endswith(".xlsx") and "2027" in n for n in names)
    assert sum("Nikoleta" in n for n in names) == 2
    assert sum("Peter" in n for n in names) == 1


def test_export_year_404_when_no_periods(client, auth_headers):
    res = client.get("/api/travels/export-year", params={"year": 1999}, headers=auth_headers)
    assert res.status_code == 404
