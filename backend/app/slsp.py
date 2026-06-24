"""Parse Slovenská sporiteľňa (George/Erste) JSON transaction exports.

The export is a JSON array of transaction objects. Amounts use Erste's scaled
form: amount.value is an integer in minor units with amount.precision decimals
(value -1250, precision 2 => -12.50). Sign is carried in value. No I/O here.
"""
import json
from datetime import date
from decimal import Decimal, InvalidOperation

# Object keys that may hold an array of transactions, if the top level is a dict.
_LIST_KEYS = ("transactions", "collection", "items", "data")


def _s(v) -> str:
    return v.strip() if isinstance(v, str) else ""


def parse_slsp_json(data: bytes) -> list[dict]:
    """Return [{txn_date, amount(Decimal), description, payee, currency}, ...].

    Raises ValueError if the document isn't a parseable JSON transaction list.
    """
    try:
        doc = json.loads(data)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError(f"Not valid JSON: {exc}") from exc

    if isinstance(doc, dict):
        for key in _LIST_KEYS:
            if isinstance(doc.get(key), list):
                doc = doc[key]
                break
    if not isinstance(doc, list):
        raise ValueError("Expected a JSON array of transactions")

    out: list[dict] = []
    for t in doc:
        if not isinstance(t, dict):
            continue
        amt = t.get("amount") or {}
        val = amt.get("value")
        if val is None:
            continue
        prec = amt.get("precision")
        if not isinstance(prec, int):
            prec = 2
        try:
            amount = Decimal(str(val)).scaleb(-prec).quantize(Decimal("0.01"))
        except (InvalidOperation, ValueError):
            continue

        raw_date = t.get("booking") or t.get("valuation") or t.get("transactionDateTime")
        if not isinstance(raw_date, str):
            continue
        try:
            txn_date = date.fromisoformat(raw_date[:10])
        except ValueError:
            continue

        description = (
            _s(t.get("reference"))
            or _s(t.get("note"))
            or _s(t.get("bookingTypeTranslation"))
        )
        payee = (
            _s(t.get("partnerName"))
            or _s(t.get("merchantName"))
            or _s(t.get("receiverName"))
            or _s(t.get("senderName"))
        )
        out.append(
            {
                "txn_date": txn_date,
                "amount": amount,
                "description": description[:255],
                "payee": payee[:120],
                "currency": _s(amt.get("currency")),
            }
        )
    return out
