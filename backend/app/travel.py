"""Travel report (cestovné): per-diem calculation and xlsx export.

Per-diem (stravné) follows Slovak meal-allowance bands by trip duration; the
rates are configurable (stored in Settings) with a per-trip override. The export
reproduces the two-sheet template: "Cestovný príkaz" + "Vyúčtovanie pracovnej
cesty" (VPC), per person per month.
"""
import io
import json
from datetime import date, time
from decimal import Decimal

from .models import Setting, Travel

RATES_KEY = "per_diem_rates"
# Slovak 2025 defaults: 5–12h, >12–18h, >18h. Below 5h -> 0.
DEFAULT_RATES = {"band1": 8.80, "band2": 13.10, "band3": 19.50}

COMPANY = "dotCUBE s.r.o"

_SK_MONTHS = {
    1: "Január", 2: "Február", 3: "Marec", 4: "Apríl", 5: "Máj", 6: "Jún",
    7: "Júl", 8: "August", 9: "September", 10: "Október", 11: "November", 12: "December",
}


def get_rates(db) -> dict:
    row = db.query(Setting).filter(Setting.key == RATES_KEY).first()
    if row and row.value:
        try:
            data = json.loads(row.value)
            return {k: float(data.get(k, DEFAULT_RATES[k])) for k in DEFAULT_RATES}
        except (ValueError, TypeError):
            pass
    return dict(DEFAULT_RATES)


def set_rates(db, rates: dict) -> dict:
    clean = {k: round(float(rates.get(k, DEFAULT_RATES[k])), 2) for k in DEFAULT_RATES}
    row = db.query(Setting).filter(Setting.key == RATES_KEY).first()
    if row:
        row.value = json.dumps(clean)
    else:
        db.add(Setting(key=RATES_KEY, value=json.dumps(clean)))
    return clean


def duration_hours(depart: time | None, arrive_home: time | None) -> float | None:
    """Trip length in hours from departure to arrival home (handles overnight)."""
    if depart is None or arrive_home is None:
        return None
    d = depart.hour * 60 + depart.minute
    a = arrive_home.hour * 60 + arrive_home.minute
    if a <= d:  # arrived after midnight
        a += 24 * 60
    return (a - d) / 60.0


def computed_per_diem(depart: time | None, arrive_home: time | None, rates: dict) -> Decimal:
    """Per-diem from trip duration using the configured bands."""
    h = duration_hours(depart, arrive_home)
    if h is None or h < 5:
        amount = 0.0
    elif h <= 12:
        amount = rates["band1"]
    elif h <= 18:
        amount = rates["band2"]
    else:
        amount = rates["band3"]
    return Decimal(str(amount)).quantize(Decimal("0.01"))


def effective_per_diem(t: Travel, rates: dict) -> Decimal:
    if t.per_diem_override is not None:
        return Decimal(t.per_diem_override).quantize(Decimal("0.01"))
    return computed_per_diem(t.depart_time, t.return_arrive_time, rates)


def _fmt_date(d: date) -> str:
    return f"{d.day}.{d.month}.{d.year}"


def _fmt_time(t: time | None) -> str:
    return f"{t.hour}:{t.minute:02d}" if t is not None else ""


def build_xlsx(name: str, address: str, year: int, month: int,
               travels: list[Travel], rates: dict) -> bytes:
    """Render the two-sheet travel report for one person and month."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, Side

    bold = Font(bold=True)
    title = Font(bold=True, size=14)
    thin = Side(style="thin")
    box = Border(left=thin, right=thin, top=thin, bottom=thin)
    center = Alignment(horizontal="center", vertical="center")

    travels = sorted(travels, key=lambda t: (t.trip_date, t.depart_time or time(0, 0)))

    wb = Workbook()

    # ---- Sheet 1: Cestovný príkaz ----
    s1 = wb.active
    s1.title = _SK_MONTHS.get(month, str(month))
    s1["B2"] = "CESTOVNÝ PRÍKAZ"; s1["B2"].font = title
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
        s1[f"B{r}"] = f"{_fmt_date(t.trip_date)} {t.from_place}, {_fmt_time(t.depart_time)}".strip()
        s1[f"C{r}"] = t.to_place
        s1[f"E{r}"] = t.purpose
        s1[f"G{r}"] = f"{_fmt_date(t.trip_date)} {t.from_place}, {_fmt_time(t.return_arrive_time)}".strip()
        for c in ("B", "C", "E", "G"):
            s1[f"{c}{r}"].border = box
        r += 1
    for col, w in {"B": 26, "C": 20, "D": 6, "E": 40, "F": 6, "G": 26}.items():
        s1.column_dimensions[col].width = w

    # ---- Sheet 2: Vyúčtovanie pracovnej cesty (VPC) ----
    s2 = wb.create_sheet("VPC")
    s2["B2"] = "VYÚČTOVANIE PRACOVNEJ CESTY"; s2["B2"].font = title
    s2["B3"] = "Firma:"; s2["C3"] = "Meno a priezvisko:"
    s2["B3"].font = bold; s2["C3"].font = bold
    s2["B4"] = COMPANY; s2["C4"] = name

    headers = ["Dátum", "ODCHOD – PRÍCHOD", "o hod.", "Použitý dopravný prostriedok", "Stravné", "Spolu"]
    for i, h in enumerate(headers):
        cell = s2.cell(row=6, column=2 + i, value=h)
        cell.font = bold; cell.alignment = center; cell.border = box
    r = 7
    total = Decimal("0.00")
    for t in travels:
        pd = effective_per_diem(t, rates)
        total += pd
        legs = [
            (f"Odchod {t.from_place}".strip(), t.depart_time, None),
            (f"Príchod {t.to_place}".strip(), t.arrive_time, None),
            (f"Odchod {t.to_place}".strip(), t.return_depart_time, None),
            (f"Príchod {t.from_place}".strip(), t.return_arrive_time, float(pd)),
        ]
        for label, tm, amount in legs:
            s2[f"B{r}"] = _fmt_date(t.trip_date)
            s2[f"C{r}"] = label
            s2[f"D{r}"] = _fmt_time(tm)
            s2[f"E{r}"] = t.transport
            if amount is not None:
                s2[f"F{r}"] = amount; s2[f"F{r}"].number_format = "0.00"
                s2[f"G{r}"] = amount; s2[f"G{r}"].number_format = "0.00"
            for c in ("B", "C", "D", "E", "F", "G"):
                s2[f"{c}{r}"].border = box
            r += 1

    r += 1
    s2[f"B{r}"] = "SPOLU"; s2[f"B{r}"].font = bold
    s2[f"F{r}"] = float(total); s2[f"F{r}"].number_format = "0.00"; s2[f"F{r}"].font = bold
    s2[f"G{r}"] = float(total); s2[f"G{r}"].number_format = "0.00"; s2[f"G{r}"].font = bold
    s2[f"B{r+1}"] = "PREDDAVOK"; s2[f"G{r+1}"] = 0.0; s2[f"G{r+1}"].number_format = "0.00"
    s2[f"B{r+2}"] = "DOPLATOK – PREPLATOK"; s2[f"B{r+2}"].font = bold
    s2[f"G{r+2}"] = float(total); s2[f"G{r+2}"].number_format = "0.00"; s2[f"G{r+2}"].font = bold

    for col, w in {"B": 14, "C": 22, "D": 9, "E": 28, "F": 10, "G": 10}.items():
        s2.column_dimensions[col].width = w

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
