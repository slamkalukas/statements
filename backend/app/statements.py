"""Statement parsing: turn an uploaded bank export into transaction lines.

Three formats are supported and auto-detected from the file content:
  - ISO 20022 CAMT.053 XML (e.g. Tatra Banka)        -> camt.parse_camt053
  - George / Erste JSON export (Slovenská sporiteľňa) -> slsp.parse_slsp_json
  - generic CSV with auto-detected columns            -> parse_csv (here)

Every parser returns the same shape:
    {txn_date: date, amount: Decimal, description: str, payee: str, currency: str}
with `amount` SIGNED (negative = money out / a payment we expect a bill for).
No I/O or persistence here — the router maps these dicts onto StatementLine rows.
"""
import csv
import io
from datetime import datetime
from decimal import Decimal, InvalidOperation

from .camt import parse_camt053
from .slsp import parse_slsp_json

_DATE_FORMATS = ["%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d"]

# Header keywords we recognize for each column (lowercased substring match).
_DATE_KEYS = ("date", "dat", "dátum", "datum", "booking")
_AMOUNT_KEYS = ("amount", "sum", "suma", "betrag", "value", "čiastka", "ciastka", "obrat")
_DESC_KEYS = ("description", "desc", "note", "reference", "text", "účel", "ucel", "poznámka", "detail")
_PAYEE_KEYS = ("payee", "partner", "counterparty", "name", "príjemca", "prijemca", "merchant", "beneficiary")


def _find_column(fieldnames: list[str], keys: tuple[str, ...]) -> str | None:
    for f in fieldnames:
        low = f.lower()
        if any(k in low for k in keys):
            return f
    return None


def _parse_date(value: str):
    value = (value or "").strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value[:19], fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(value[:19]).date()
    except ValueError:
        return None


def _parse_amount(value: str) -> Decimal | None:
    cleaned = (value or "").strip().replace(" ", "").replace(" ", "")
    for sym in ("€", "$", "£", "EUR", "USD", "GBP", "Kč", "CZK"):
        cleaned = cleaned.replace(sym, "")
    if not cleaned:
        return None
    # Normalize European decimals: "1.234,56" -> "1234.56"; "1234,56" -> "1234.56".
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    try:
        return Decimal(cleaned).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def parse_csv(data: bytes) -> list[dict]:
    """Auto-detect date/amount/description/payee columns from the CSV header."""
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("latin-1")

    # Sniff the delimiter (comma vs semicolon are both common in EU exports).
    sample = text[:2048]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if not reader.fieldnames:
        raise ValueError("CSV has no header row")

    fields = [f for f in reader.fieldnames if f]
    date_col = _find_column(fields, _DATE_KEYS)
    amount_col = _find_column(fields, _AMOUNT_KEYS)
    if not date_col or not amount_col:
        raise ValueError("Could not find date and amount columns in the CSV header")
    desc_col = _find_column(fields, _DESC_KEYS)
    payee_col = _find_column(fields, _PAYEE_KEYS)

    out: list[dict] = []
    for row in reader:
        txn_date = _parse_date(row.get(date_col, ""))
        amount = _parse_amount(row.get(amount_col, ""))
        if txn_date is None or amount is None:
            continue
        out.append(
            {
                "txn_date": txn_date,
                "amount": amount,
                "description": (row.get(desc_col, "") if desc_col else "").strip()[:255],
                "payee": (row.get(payee_col, "") if payee_col else "").strip()[:120],
                "currency": "",
            }
        )
    return out


def parse_statement(data: bytes) -> tuple[list[dict], str]:
    """Detect the format from content and parse. Returns (rows, format_name).

    Raises ValueError with a helpful message if nothing parses.
    """
    head = data.lstrip()[:1]
    errors: list[str] = []

    if head == b"<":
        try:
            return parse_camt053(data), "CAMT.053 XML"
        except ValueError as exc:
            errors.append(f"XML: {exc}")
    if head in (b"{", b"["):
        try:
            return parse_slsp_json(data), "George JSON"
        except ValueError as exc:
            errors.append(f"JSON: {exc}")

    # Fall back to CSV (and also try it if the content sniff was inconclusive).
    try:
        rows = parse_csv(data)
        if rows:
            return rows, "CSV"
        errors.append("CSV: no transaction rows found")
    except ValueError as exc:
        errors.append(f"CSV: {exc}")

    raise ValueError("; ".join(errors) or "Unrecognized statement format")
