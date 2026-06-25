"""Parse OFX 2.x (XML) bank/credit-card statements, e.g. Tatra Banka card exports.

Namespace-agnostic (matches by local element name) so it tolerates the OFX
default namespace and bank-specific extension namespaces (e.g. TB:). Returns the
same dict shape as the other parsers; no I/O here.

Transactions live in <STMTTRN> elements:
    <TRNTYPE>DEBIT|CREDIT</TRNTYPE>  <DTPOSTED>YYYYMMDD</DTPOSTED>
    <TRNAMT>21.40</TRNAMT>  <NAME>…</NAME>  <CURRENCY>EUR</CURRENCY>
Amount sign follows TRNTYPE (DEBIT = money out = negative), since some exports
report TRNAMT as a positive magnitude.
"""
import xml.etree.ElementTree as ET
from datetime import date
from decimal import Decimal, InvalidOperation


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child(el, name):
    if el is None:
        return None
    for c in el:
        if _local(c.tag) == name:
            return c
    return None


def _text(el) -> str:
    return (el.text or "").strip() if el is not None else ""


def _parse_date(s: str) -> date | None:
    digits = "".join(ch for ch in (s or "") if ch.isdigit())
    if len(digits) < 8:
        return None
    try:
        return date(int(digits[0:4]), int(digits[4:6]), int(digits[6:8]))
    except ValueError:
        return None


def parse_ofx(data: bytes) -> list[dict]:
    """Return a list of {txn_date, amount(Decimal), description, payee, currency}.

    Raises ValueError if the document isn't parseable XML.
    """
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise ValueError(f"Not valid XML: {exc}") from exc

    out: list[dict] = []
    for tr in (e for e in root.iter() if _local(e.tag) == "STMTTRN"):
        raw_amt = _text(_child(tr, "TRNAMT"))
        try:
            amount = Decimal(raw_amt).quantize(Decimal("0.01"))
        except (InvalidOperation, ValueError):
            continue

        trntype = _text(_child(tr, "TRNTYPE")).upper()
        if trntype == "DEBIT":
            amount = -abs(amount)
        elif trntype == "CREDIT":
            amount = abs(amount)
        # else: keep TRNAMT's own sign

        txn_date = _parse_date(_text(_child(tr, "DTPOSTED"))) or _parse_date(_text(_child(tr, "DTAVAIL")))
        if txn_date is None:
            continue

        name = _text(_child(tr, "NAME")) or _text(_child(tr, "MEMO"))
        currency = _text(_child(tr, "CURRENCY"))

        out.append(
            {
                "txn_date": txn_date,
                "amount": amount,
                "description": name[:255],
                "payee": name[:120],
                "currency": currency,
            }
        )
    return out
