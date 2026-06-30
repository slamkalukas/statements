"""Vehicle logbook (Kniha jázd): xlsx export matching the company format."""
import io
from datetime import datetime

from .models import CarTrip, Vehicle
from .travel import COMPANY

_SK_MONTHS = {
    1: "Január", 2: "Február", 3: "Marec", 4: "Apríl", 5: "Máj", 6: "Jún",
    7: "Júl", 8: "August", 9: "September", 10: "Október", 11: "November", 12: "December",
}


def fuel_unit(vehicle: Vehicle) -> str:
    return "kWh" if "elektr" in (vehicle.fuel_type or "").lower() else "L"


def trip_km(trip: CarTrip) -> int | None:
    if trip.odometer_start is not None and trip.odometer_end is not None:
        return trip.odometer_end - trip.odometer_start
    return None


def trip_cost(trip: CarTrip, vehicle: Vehicle) -> float | None:
    km = trip_km(trip)
    if km is None or vehicle.consumption is None:
        return None
    price = float(trip.fuel_price_override or vehicle.fuel_price or 0)
    if not price:
        return None
    return round(km * float(vehicle.consumption) / 100 * price, 2)


def build_xlsx(vehicle: Vehicle, trips: list[CarTrip]) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, Side

    wb = Workbook()
    ws = wb.active
    unit = fuel_unit(vehicle)
    bold = Font(bold=True)
    thin = Side(style="thin")
    box = Border(left=thin, right=thin, top=thin, bottom=thin)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)

    title = f"{vehicle.ecv} {vehicle.manufacturer} {vehicle.car_model}".strip()
    ws.title = title[:31]

    meta = [
        ("Kniha jázd", None),
        ("Firma", COMPANY),
        ("Dátum exportu", datetime.today().strftime("%d.%m.%Y")),
        ("Vlastníctvo vozidla", vehicle.ownership or "Firemné"),
        ("EČV", vehicle.ecv),
        ("VIN", vehicle.vin or ""),
        ("Výrobca", vehicle.manufacturer or ""),
        ("Model", vehicle.car_model or ""),
        ("Palivo", vehicle.fuel_type or ""),
        (f"Spotreba [{unit}/100km]",
         float(vehicle.consumption) if vehicle.consumption is not None else None),
        ("Dátum zaradenia do majetku",
         vehicle.date_added.strftime("%d.%m.%Y") if vehicle.date_added else ""),
        ("Spôsob výpočtu trás", "Spotreba podľa technického preukazu"),
    ]
    for r, (label, value) in enumerate(meta, start=1):
        ws.cell(r, 1).value = label
        ws.cell(r, 1).font = bold
        if value is not None:
            ws.cell(r, 2).value = value

    header_row = 13
    headers = [
        "Číslo záznamu o jazde",
        "Dátum a čas začiatku jazdy",
        "Dátum a čas skončenia jazdy",
        "Účel jazdy",
        "Jazda / cesta",
        "Počiatočný stav odometra",
        "Konečný stav odometra",
        "Počet najazdených km",
        f"Cena PHM [EUR/{unit}]",
        "Typ jazdy",
        "Vodič",
        "Udalosti",
        "Náklady na cestu [EUR]",
    ]
    for c, h in enumerate(headers, start=1):
        cell = ws.cell(header_row, c, value=h)
        cell.font = bold
        cell.border = box
        cell.alignment = center

    trips_sorted = sorted(trips, key=lambda t: t.start_dt)
    for i, trip in enumerate(trips_sorted, start=1):
        r = header_row + i
        km = trip_km(trip)
        cost = trip_cost(trip, vehicle)
        fp = float(trip.fuel_price_override or vehicle.fuel_price or 0) or None
        row_data = [
            trip.journey_number,
            trip.start_dt.strftime("%d.%m.%Y %H:%M") if trip.start_dt else "",
            trip.end_dt.strftime("%d.%m.%Y %H:%M") if trip.end_dt else "",
            trip.purpose,
            trip.route,
            trip.odometer_start,
            trip.odometer_end,
            km,
            fp,
            trip.trip_type,
            trip.driver_name,
            trip.events,
            cost,
        ]
        for c, val in enumerate(row_data, start=1):
            cell = ws.cell(r, c, value=val)
            cell.border = box

    widths = [15, 20, 20, 30, 50, 14, 14, 10, 12, 12, 20, 20, 16]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[ws.cell(1, i).column_letter].width = w

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
