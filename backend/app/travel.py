"""Travel report (cestovné): per-diem calculation and xlsx export.

Per-diem (stravné) follows Slovak meal-allowance bands by trip duration; for
multi-leg/international trips each leg can carry its own per_diem value and the
trip total is their sum. The export reproduces the two-sheet template:
"Cestovný príkaz" + "Vyúčtovanie pracovnej cesty" (VPC), per person per month.
"""
import io
import json
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from .models import Setting, Travel

RATES_KEY = "per_diem_rates"
# Slovak 2025 defaults: 5–12h, >12–18h, >18h. Below 5h -> 0.
DEFAULT_RATES = {"band1": 8.80, "band2": 13.10, "band3": 19.50}

# Zahraničné stravné: a basic daily rate per country, apportioned per calendar
# day by time spent abroad. Rates are set by an MF SR opatrenie and change
# during the year, so they are configured in Settings rather than hardcoded.
FOREIGN_RATES_KEY = "foreign_per_diem_rates"

# Whether the Slovak part of a day on a foreign trip also earns domestic stravné
# (only when those hours reach the 5 h threshold on their own).
DOMESTIC_TOPUP_KEY = "per_diem_domestic_topup"

# Both rate tables are effective-dated: a row applies from its valid_from until
# superseded by a later one, so re-rating a country next quarter does not rewrite
# what last quarter's trips reported. A row with no valid_from applies from the
# beginning of time, which is how pre-dating rows are read back.
BEGINNING = date.min

COMPANY = "dotCUBE s.r.o"

# Shown on the report where a leg has no country of its own — the side of the
# border the traveller starts and ends on.
HOME_COUNTRY = "SK"

_SK_MONTHS = {
    1: "Január", 2: "Február", 3: "Marec", 4: "Apríl", 5: "Máj", 6: "Jún",
    7: "Júl", 8: "August", 9: "September", 10: "Október", 11: "November", 12: "December",
}

_COMPANY_CAR_MARKERS = ("firemn", "služobn", "sluzob")


def is_company_car_transport(transport: str | None) -> bool:
    """True for transport labels that mean "company car" (Auto firemné/služobné),
    matched loosely enough to survive diacritics/spelling variants."""
    t = (transport or "").lower()
    return any(marker in t for marker in _COMPANY_CAR_MARKERS)


def _parse_valid_from(value) -> date:
    if not value:
        return BEGINNING
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return BEGINNING


def _effective(rows: list[dict], on: date):
    """The last row whose valid_from is not after `on`. Rows must be sorted."""
    chosen = None
    for row in rows:
        if row["valid_from"] <= on:
            chosen = row
        else:
            break
    return chosen


def get_rate_history(db) -> list[dict]:
    """Domestic bands over time: [{valid_from, band1, band2, band3}] oldest first."""
    row = db.query(Setting).filter(Setting.key == RATES_KEY).first()
    if not (row and row.value):
        return [{"valid_from": BEGINNING, **DEFAULT_RATES}]
    try:
        data = json.loads(row.value)
    except (ValueError, TypeError):
        return [{"valid_from": BEGINNING, **DEFAULT_RATES}]
    # Pre-dating shape: a single {band1, band2, band3} dict with no history.
    if isinstance(data, dict):
        data = [data]
    history = _clean_rate_history(data if isinstance(data, list) else [])
    return history or [{"valid_from": BEGINNING, **DEFAULT_RATES}]


def _clean_rate_history(rows) -> list[dict]:
    out: list[dict] = []
    seen: set[date] = set()
    for item in rows:
        if not isinstance(item, dict):
            continue
        valid_from = _parse_valid_from(item.get("valid_from"))
        if valid_from in seen:
            continue
        seen.add(valid_from)
        bands = {}
        for k in DEFAULT_RATES:
            try:
                bands[k] = round(float(item.get(k, DEFAULT_RATES[k])), 2)
            except (TypeError, ValueError):
                bands[k] = DEFAULT_RATES[k]
        out.append({"valid_from": valid_from, **bands})
    return sorted(out, key=lambda r: r["valid_from"])


def set_rate_history(db, rows) -> list[dict]:
    clean = _clean_rate_history(rows) or [{"valid_from": BEGINNING, **DEFAULT_RATES}]
    payload = json.dumps([
        {**{k: r[k] for k in DEFAULT_RATES},
         "valid_from": None if r["valid_from"] == BEGINNING else r["valid_from"].isoformat()}
        for r in clean
    ])
    row = db.query(Setting).filter(Setting.key == RATES_KEY).first()
    if row:
        row.value = payload
    else:
        db.add(Setting(key=RATES_KEY, value=payload))
    return clean


def get_rates(db, on: date | None = None) -> dict:
    """The domestic bands in force on a date (today when not given)."""
    history = get_rate_history(db)
    chosen = _effective(history, on or date.today()) or history[0]
    return {k: chosen[k] for k in DEFAULT_RATES}


def set_rates(db, rates: dict) -> dict:
    """Replace the whole domestic history with one open-ended set of bands."""
    clean = set_rate_history(db, [{**rates, "valid_from": None}])
    return {k: clean[0][k] for k in DEFAULT_RATES}


def get_domestic_topup(db) -> bool:
    row = db.query(Setting).filter(Setting.key == DOMESTIC_TOPUP_KEY).first()
    return bool(row and row.value == "1")


def set_domestic_topup(db, enabled: bool) -> bool:
    row = db.query(Setting).filter(Setting.key == DOMESTIC_TOPUP_KEY).first()
    if row:
        row.value = "1" if enabled else "0"
    else:
        db.add(Setting(key=DOMESTIC_TOPUP_KEY, value="1" if enabled else "0"))
    return enabled


def get_foreign_rates(db) -> list[dict]:
    """Configured foreign daily rates: [{code, name, rate}], sorted by name."""
    row = db.query(Setting).filter(Setting.key == FOREIGN_RATES_KEY).first()
    if not (row and row.value):
        return []
    try:
        data = json.loads(row.value)
    except (ValueError, TypeError):
        return []
    return _clean_foreign_rates(data if isinstance(data, list) else [])


def _clean_foreign_rates(rows) -> list[dict]:
    """Normalise rate rows. A country may appear several times with different
    valid_from dates — that is its rate history, not a duplicate."""
    out: list[dict] = []
    seen: set[tuple[str, date]] = set()
    for item in rows:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or "").strip().upper()
        if not code:
            continue
        valid_from = _parse_valid_from(item.get("valid_from"))
        if (code, valid_from) in seen:
            continue
        seen.add((code, valid_from))
        try:
            rate = round(float(item.get("rate") or 0), 2)
        except (TypeError, ValueError):
            rate = 0.0
        out.append({
            "code": code,
            "name": str(item.get("name") or "").strip() or code,
            "rate": rate,
            "valid_from": valid_from,
        })
    return sorted(out, key=lambda r: (r["name"], r["valid_from"]))


def set_foreign_rates(db, rows) -> list[dict]:
    clean = _clean_foreign_rates(rows)
    payload = json.dumps([
        {"code": r["code"], "name": r["name"], "rate": r["rate"],
         "valid_from": None if r["valid_from"] == BEGINNING else r["valid_from"].isoformat()}
        for r in clean
    ])
    row = db.query(Setting).filter(Setting.key == FOREIGN_RATES_KEY).first()
    if row:
        row.value = payload
    else:
        db.add(Setting(key=FOREIGN_RATES_KEY, value=payload))
    return clean


def foreign_rate_for(code: str, foreign_rates: list[dict], on: date | None = None) -> float:
    """The daily rate in force for a country on a date, or 0 when not configured."""
    wanted = (code or "").strip().upper()
    if not wanted:
        return 0.0
    when = on or date.today()
    rows = sorted(
        (r for r in (foreign_rates or []) if r.get("code") == wanted),
        key=lambda r: r["valid_from"],
    )
    chosen = _effective(rows, when)
    return float(chosen["rate"]) if chosen else 0.0


def foreign_countries(foreign_rates: list[dict]) -> list[dict]:
    """One entry per configured country (its currently-latest name), for pickers."""
    by_code: dict[str, dict] = {}
    for row in sorted(foreign_rates or [], key=lambda r: r["valid_from"]):
        by_code[row["code"]] = row
    return sorted(by_code.values(), key=lambda r: r["name"])


def duration_hours(date_from: date, date_to: date | None,
                   first_depart: time | None, last_arrive: time | None) -> float | None:
    """Trip length in hours: from first leg's departure to last leg's arrival home."""
    if first_depart is None or last_arrive is None:
        return None
    end = date_to or date_from
    span_days = (end - date_from).days
    d = first_depart.hour * 60 + first_depart.minute
    a = last_arrive.hour * 60 + last_arrive.minute
    total = span_days * 24 * 60 + (a - d)
    if total <= 0:
        total += 24 * 60
    return total / 60.0


def _band_amount(hours: float, rates: dict) -> float:
    if hours < 5:
        return 0.0
    if hours <= 12:
        return rates["band1"]
    if hours <= 18:
        return rates["band2"]
    return rates["band3"]


def computed_per_diem(date_from: date, date_to: date | None,
                      first_depart: time | None, last_arrive: time | None,
                      rates: dict) -> Decimal:
    """Per-diem from trip duration using the configured bands. For multi-day trips
    each full 24h counts as a whole-day allowance (band3) plus the remainder by band."""
    h = duration_hours(date_from, date_to, first_depart, last_arrive)
    if h is None:
        return Decimal("0.00")
    full_days = int(h // 24)
    remainder = h - full_days * 24
    amount = full_days * rates["band3"] + _band_amount(remainder, rates)
    return Decimal(str(amount)).quantize(Decimal("0.01"))


def _leg_times(t: Travel) -> tuple[time | None, time | None]:
    """Return (first leg depart_time, last leg arrive_time) for duration calculation."""
    if not t.legs:
        return None, None
    return t.legs[0].depart_time, t.legs[-1].arrive_time


def _foreign_fraction(hours: float) -> Decimal:
    """Share of the daily rate earned by time abroad in one calendar day:
    25 % up to 6 h, 50 % over 6 and up to 12 h, 100 % over 12 h."""
    if hours <= 6:
        return Decimal("0.25")
    if hours <= 12:
        return Decimal("0.50")
    return Decimal("1")


class RateBook:
    """Resolves the rates in force on a given day, so re-rating a country later
    does not change what an earlier trip reports."""

    def __init__(self, domestic_history: list[dict], foreign_rates: list[dict],
                 domestic_topup: bool = False):
        self.domestic_history = domestic_history or [{"valid_from": BEGINNING, **DEFAULT_RATES}]
        self.foreign_rates = foreign_rates or []
        self.domestic_topup = domestic_topup

    def domestic(self, on: date) -> dict:
        chosen = _effective(self.domestic_history, on) or self.domestic_history[0]
        return {k: chosen[k] for k in DEFAULT_RATES}

    def foreign(self, code: str, on: date) -> float:
        return foreign_rate_for(code, self.foreign_rates, on)


def leg_effective_date(t: Travel, index: int, leg) -> date:
    """Which calendar day a leg happens on: the trip's start for the first leg,
    its end for the last, and the leg's own date in between."""
    end = t.end_date or t.trip_date
    if index == 0:
        return t.trip_date
    if index == len(t.legs) - 1:
        return end
    return leg.leg_date or t.trip_date


def is_foreign_trip(t: Travel) -> bool:
    return any((leg.country or "").strip() for leg in t.legs if leg.kind != "stay")


def _presence_intervals(t: Travel) -> list[tuple[datetime, datetime, str]]:
    """Where the traveller was, as (from, to, country) spans.

    You are in a leg's destination country from the moment that leg crosses the
    border — its border_time when recorded, otherwise its arrival, which is what
    the law counts for a flight. So the journey home stays abroad until it lands
    or re-crosses. A stay normally inherits wherever you last arrived, but may
    name its own country, which then applies from the start of that stay.
    Country "" means home.
    """
    legs = list(t.legs)
    moves = [(i, l) for i, l in enumerate(legs) if l.kind != "stay"]
    if not moves:
        return []
    first_i, first = moves[0]
    last_i, last = moves[-1]
    if first.depart_time is None or last.arrive_time is None:
        return []

    start = datetime.combine(leg_effective_date(t, first_i, first), first.depart_time)
    end = datetime.combine(leg_effective_date(t, last_i, last), last.arrive_time)
    if end <= start:
        return []

    out: list[tuple[datetime, datetime, str]] = []
    cursor, country = start, ""
    for i, leg in enumerate(legs):
        leg_country = (leg.country or "").strip().upper()
        if leg.kind == "stay":
            if not leg_country:
                continue  # inherits — nothing moves, nothing to switch
            switch_at = datetime.combine(
                leg_effective_date(t, i, leg), leg.depart_time or time(0, 0)
            )
        else:
            # Overland you change country at the border, not on arrival — the
            # difference is what splits a day's domestic and foreign hours.
            crossing = leg.border_time or leg.arrive_time
            if crossing is None:
                continue
            switch_at = datetime.combine(leg_effective_date(t, i, leg), crossing)

        switch_at = min(max(switch_at, cursor), end)
        if switch_at > cursor:
            out.append((cursor, switch_at, country))
            cursor = switch_at
        country = leg_country
    if cursor < end:
        out.append((cursor, end, country))
    return out


def per_diem_days(t: Travel, book: RateBook) -> list[dict]:
    """One line per calendar day of a foreign trip.

    Per day: the band is set by the total hours abroad, and the rate by the
    country where most of those hours were spent. The Slovak part of the day
    earns domestic stravné on its own hours only when the top-up setting is on
    — the same hours are never paid twice.
    """
    minutes: dict[date, dict[str, int]] = {}
    for start, end, country in _presence_intervals(t):
        cursor = start
        while cursor < end:
            next_midnight = datetime.combine(cursor.date() + timedelta(days=1), time(0, 0))
            chunk_end = min(next_midnight, end)
            day = minutes.setdefault(cursor.date(), {})
            day[country] = day.get(country, 0) + int((chunk_end - cursor).total_seconds() // 60)
            cursor = chunk_end

    lines: list[dict] = []
    for day in sorted(minutes):
        by_country = minutes[day]
        abroad = {c: m for c, m in by_country.items() if c}
        abroad_min = sum(abroad.values())
        home_min = by_country.get("", 0)

        amount = Decimal("0.00")
        country = ""
        rate = 0.0
        if abroad_min:
            # Most hours that day decides which country's rate applies.
            country = max(sorted(abroad), key=lambda c: abroad[c])
            rate = book.foreign(country, day)
            amount += Decimal(str(rate)) * _foreign_fraction(abroad_min / 60)

        home_amount = Decimal("0.00")
        if home_min and (not abroad_min or book.domestic_topup):
            home_amount = Decimal(str(_band_amount(home_min / 60, book.domestic(day))))
            amount += home_amount

        lines.append({
            "date": day,
            "country": country,
            "rate": rate,
            "abroad_hours": round(abroad_min / 60, 2),
            "home_hours": round(home_min / 60, 2),
            "home_amount": home_amount.quantize(Decimal("0.01")),
            "amount": amount.quantize(Decimal("0.01")),
        })
    return lines


def computed_trip_per_diem(t: Travel, book: RateBook) -> Decimal:
    """Duration-derived per-diem: the per-day foreign engine once any leg has a
    country, the domestic duration bands otherwise."""
    if is_foreign_trip(t):
        total = sum((line["amount"] for line in per_diem_days(t, book)), Decimal("0.00"))
        return total.quantize(Decimal("0.01"))
    first_depart, last_arrive = _leg_times(t)
    return computed_per_diem(
        t.trip_date, t.end_date, first_depart, last_arrive, book.domestic(t.trip_date)
    )


def effective_per_diem(t: Travel, book: RateBook) -> Decimal:
    """Sum of leg per_diems when any leg has one set; otherwise compute from duration."""
    if t.legs and any(leg.per_diem is not None for leg in t.legs):
        total = sum(
            Decimal(str(leg.per_diem)) for leg in t.legs if leg.per_diem is not None
        )
        return total.quantize(Decimal("0.01"))
    return computed_trip_per_diem(t, book)


def load_rate_book(db) -> RateBook:
    """Everything the per-diem calculation needs, read once per request."""
    return RateBook(get_rate_history(db), get_foreign_rates(db), get_domestic_topup(db))


def _fmt_date(d: date) -> str:
    return f"{d.day}.{d.month}.{d.year}"


def _fmt_time(t: time | None) -> str:
    return f"{t.hour}:{t.minute:02d}" if t is not None else ""


def _home_place(t: Travel) -> str:
    return t.legs[0].from_place if t.legs else ""


def _write_leg_money(sheet, row: int, leg, trip_pd: float | None,
                     is_last_leg: bool) -> tuple[float, float]:
    """Stravné / výdavky / row total for one leg row, returning both amounts so
    the caller can total the columns. Per-leg stravné wins; the duration-derived
    trip total lands on the trip's last row when no leg sets one.

    Amounts are written as numbers, not formulas. A formula carries no result
    until the reader recalculates, and the exported sheet is a record that has
    to show its figures in whatever the accountant opens it with.
    """
    pd_value = None
    if leg.per_diem is not None:
        pd_value = float(leg.per_diem)
    elif is_last_leg and trip_pd is not None:
        pd_value = trip_pd
    expense = float(leg.expense) if leg.expense is not None else None

    if pd_value is not None:
        sheet.cell(row, 6).value = pd_value
        sheet.cell(row, 6).number_format = "0.00"
    if expense is not None:
        sheet.cell(row, 7).value = expense
        sheet.cell(row, 7).number_format = "0.00"
    sheet.cell(row, 8).value = round((pd_value or 0.0) + (expense or 0.0), 2)
    sheet.cell(row, 8).number_format = "0.00"
    return pd_value or 0.0, expense or 0.0


def build_xlsx(name: str, address: str, year: int, month: int,
               travels: list[Travel], book: RateBook) -> bytes:
    """Render the two-sheet travel report for one person and month."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, Side

    bold = Font(bold=True)
    title_font = Font(bold=True, size=14)
    thin = Side(style="thin")
    box = Border(left=thin, right=thin, top=thin, bottom=thin)
    center = Alignment(horizontal="center", vertical="center")

    travels = sorted(travels, key=lambda t: (t.trip_date, t.legs[0].depart_time if t.legs else time(0, 0)))

    wb = Workbook()

    # ---- Sheet 1: Cestovný príkaz ----
    s1 = wb.active
    s1.title = _SK_MONTHS.get(month, str(month))
    s1["B2"] = "CESTOVNÝ PRÍKAZ"; s1["B2"].font = title_font
    s1["B3"] = "Firma:"; s1["C3"] = "Meno a priezvisko:"; s1["E3"] = "Bydlisko:"
    for c in ("B3", "C3", "E3"):
        s1[c].font = bold
    s1["B4"] = COMPANY; s1["C4"] = name; s1["E4"] = address

    s1["B6"] = "Začiatok cesty:"; s1["C6"] = "Miesto rokovania:"
    s1["E6"] = "Účel cesty:"; s1["G6"] = "Koniec cesty:"
    for c in ("B6", "C6", "E6", "G6"):
        s1[c].font = bold
    r = 7
    for t in travels:
        end = t.end_date or t.trip_date
        first_leg = t.legs[0] if t.legs else None
        last_leg = t.legs[-1] if t.legs else None
        s1[f"B{r}"] = f"{_fmt_date(t.trip_date)} {first_leg.from_place if first_leg else ''}, {_fmt_time(first_leg.depart_time if first_leg else None)}".strip(", ")
        # "Miesto rokovania" is left blank to fill in by hand: on a multi-leg trip
        # the legs don't say which stop was the one that mattered, and guessing it
        # (previously: every destination, joined) was more misleading than useful.
        s1[f"E{r}"] = t.purpose
        s1[f"G{r}"] = f"{_fmt_date(end)} {last_leg.to_place if last_leg else ''}, {_fmt_time(last_leg.arrive_time if last_leg else None)}".strip(", ")
        for c in ("B", "C", "E", "G"):
            s1[f"{c}{r}"].border = box
        r += 1
    for col, w in {"B": 26, "C": 20, "D": 6, "E": 40, "F": 6, "G": 26}.items():
        s1.column_dimensions[col].width = w

    # ---- Sheet 2: Vyúčtovanie pracovnej cesty (VPC) ----
    # Columns: B=Dátum C=ODCHOD–PRÍCHOD D=o hod. E=Dopravný prostriedok
    #          F=Stravné  G=Výdavky  H=Spolu
    s2 = wb.create_sheet("VPC")
    s2["B2"] = "VYÚČTOVANIE PRACOVNEJ CESTY"; s2["B2"].font = title_font
    s2["B3"] = "Firma:"; s2["C3"] = "Meno a priezvisko:"
    s2["B3"].font = bold; s2["C3"].font = bold
    s2["B4"] = COMPANY; s2["C4"] = name

    headers = ["Dátum", "ODCHOD – PRÍCHOD", "o hod.", "Použitý dopravný prostriedok",
               "Stravné", "Výdavky", "Spolu"]
    for i, h in enumerate(headers):
        cell = s2.cell(row=6, column=2 + i, value=h)
        cell.font = bold; cell.alignment = center; cell.border = box

    data_start = 7
    r = data_start
    sum_per_diem = sum_expense = 0.0

    for t in travels:
        end = t.end_date or t.trip_date
        has_leg_per_diem = any(leg.per_diem is not None for leg in t.legs)
        trip_pd = float(effective_per_diem(t, book)) if not has_leg_per_diem else None
        country_now = ""  # tracks where the traveller is, to label border crossings

        for i, leg in enumerate(t.legs):
            is_last_leg = (i == len(t.legs) - 1)
            # First leg → trip_date; last leg → end_date; middle legs → leg_date or trip_date
            if i == 0:
                effective_date = t.trip_date
            elif is_last_leg:
                effective_date = end
            else:
                effective_date = leg.leg_date or t.trip_date
            leg_date = _fmt_date(effective_date)
            arrive_date = leg_date

            if leg.kind == "stay":
                # A day spent in one place — a single row, no Odchod/Príchod pair.
                place = leg.to_place or leg.from_place
                label = f"Pobyt {place}".strip() if place else "Pobyt"
                if leg.note:
                    label = f"{label} — {leg.note}"
                s2.cell(r, 2).value = leg_date
                s2.cell(r, 3).value = label
                if leg.depart_time or leg.arrive_time:
                    s2.cell(r, 4).value = (
                        f"{_fmt_time(leg.depart_time)}–{_fmt_time(leg.arrive_time)}".strip("–")
                    )
                pd_amount, exp_amount = _write_leg_money(s2, r, leg, trip_pd, is_last_leg)
                sum_per_diem += pd_amount
                sum_expense += exp_amount
                for col in range(2, 9):
                    s2.cell(r, col).border = box
                r += 1
                if leg.country:
                    country_now = leg.country
                continue

            # Row 1: Odchod from_place at depart_time
            s2.cell(r, 2).value = leg_date
            s2.cell(r, 3).value = f"Odchod {leg.from_place}".strip()
            s2.cell(r, 4).value = _fmt_time(leg.depart_time)
            s2.cell(r, 5).value = leg.transport
            for col in range(2, 9):
                s2.cell(r, col).border = box
            r += 1

            # Between them, when travelling overland: the state border crossing,
            # which is what decides how a day splits between the two countries.
            if leg.border_time is not None:
                s2.cell(r, 2).value = leg_date
                s2.cell(r, 3).value = (
                    f"Prechod hranice {country_now or HOME_COUNTRY} → {leg.country or HOME_COUNTRY}"
                )
                s2.cell(r, 4).value = _fmt_time(leg.border_time)
                for col in range(2, 9):
                    s2.cell(r, col).border = box
                r += 1
            country_now = leg.country or ""

            # Row 2: Príchod to_place at arrive_time — expense/per_diem go here
            s2.cell(r, 2).value = arrive_date
            arrival = f"Príchod {leg.to_place}".strip()
            s2.cell(r, 3).value = f"{arrival} — {leg.note}" if leg.note else arrival
            s2.cell(r, 4).value = _fmt_time(leg.arrive_time)
            pd_amount, exp_amount = _write_leg_money(s2, r, leg, trip_pd, is_last_leg)
            sum_per_diem += pd_amount
            sum_expense += exp_amount
            for col in range(2, 9):
                s2.cell(r, col).border = box
            r += 1

        if len(travels) > 1 and t is not travels[-1]:
            r += 1  # blank row between trips

    r += 1  # blank row before totals

    total = round(sum_per_diem + sum_expense, 2)
    s2.cell(r, 2).value = "SPOLU"; s2.cell(r, 2).font = bold
    s2.cell(r, 6).value = round(sum_per_diem, 2)
    s2.cell(r, 6).number_format = "0.00"; s2.cell(r, 6).font = bold
    s2.cell(r, 7).value = round(sum_expense, 2)
    s2.cell(r, 7).number_format = "0.00"; s2.cell(r, 7).font = bold
    s2.cell(r, 8).value = total
    s2.cell(r, 8).number_format = "0.00"; s2.cell(r, 8).font = bold

    # An advance is filled in by hand, so the balance below assumes none.
    preddavok = 0.0
    preddavok_row = r + 1
    s2.cell(preddavok_row, 2).value = "PREDDAVOK"
    s2.cell(preddavok_row, 8).value = preddavok
    s2.cell(preddavok_row, 8).number_format = "0.00"

    doplatok_row = r + 2
    s2.cell(doplatok_row, 2).value = "DOPLATOK – PREPLATOK"; s2.cell(doplatok_row, 2).font = bold
    s2.cell(doplatok_row, 8).value = round(total - preddavok, 2)
    s2.cell(doplatok_row, 8).number_format = "0.00"; s2.cell(doplatok_row, 8).font = bold

    for col, w in {"B": 14, "C": 28, "D": 9, "E": 28, "F": 10, "G": 10, "H": 10}.items():
        s2.column_dimensions[col].width = w

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
