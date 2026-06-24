"""Parse ISO 20022 CAMT.053 bank statements (e.g. Tatra Banka exports).

Namespace-agnostic (matches by local element name) so it tolerates the
camt.053.001.02/.04/.08 variants. Returns plain dicts the importer maps to
statement lines — no I/O, no network, no persistence here.
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


def _path(el, *names):
    cur = el
    for n in names:
        cur = _child(cur, n)
        if cur is None:
            return None
    return cur


def _text(el) -> str:
    return (el.text or "").strip() if el is not None else ""


def _parse_date(s: str) -> date | None:
    s = (s or "").strip()
    if not s:
        return None
    try:
        # Handles "2026-06-23" and "2026-06-23T10:00:00..." alike.
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def parse_camt053(data: bytes) -> list[dict]:
    """Return a list of {txn_date, amount(Decimal), description, payee, currency}.

    Raises ValueError if the document isn't parseable XML.
    """
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise ValueError(f"Not valid XML: {exc}") from exc

    entries = [e for e in root.iter() if _local(e.tag) == "Ntry"]
    out: list[dict] = []
    for n in entries:
        amt_el = _child(n, "Amt")
        cd = _text(_child(n, "CdtDbtInd"))  # CRDT (in) / DBIT (out)
        if amt_el is None or cd not in ("CRDT", "DBIT"):
            continue
        try:
            amount = Decimal((amt_el.text or "").strip()).quantize(Decimal("0.01"))
        except (InvalidOperation, AttributeError):
            continue
        if cd == "DBIT":
            amount = -amount

        # Note: ElementTree elements are "falsy" when they have no children, so
        # never use `a or b` on them — pick explicitly with `is not None`.
        bookg = _path(n, "BookgDt", "Dt")
        if bookg is None:
            bookg = _path(n, "BookgDt", "DtTm")
        txn_date = _parse_date(_text(bookg))
        if txn_date is None:
            vald = _path(n, "ValDt", "Dt")
            if vald is None:
                vald = _path(n, "ValDt", "DtTm")
            txn_date = _parse_date(_text(vald))
        if txn_date is None:
            continue

        currency = amt_el.get("Ccy") or ""
        tx = _path(n, "NtryDtls", "TxDtls")

        # Description: remittance text if present, else the bank's summary line.
        ustrd_parts = []
        rmt = _child(tx, "RmtInf") if tx is not None else None
        if rmt is not None:
            ustrd_parts = [_text(c) for c in rmt if _local(c.tag) == "Ustrd" and _text(c)]
        description = " ".join(ustrd_parts) or _text(_child(n, "AddtlNtryInf"))

        # Payee: the counterparty. Outgoing (DBIT) -> creditor; incoming -> debtor.
        payee = ""
        rp = _path(tx, "RltdPties") if tx is not None else None
        if rp is not None:
            primary = "Cdtr" if cd == "DBIT" else "Dbtr"
            for who in (primary, "TradgPty", "InitgPty"):
                nm = _path(rp, who, "Nm")
                if nm is not None and _text(nm):
                    payee = _text(nm)
                    break

        out.append(
            {
                "txn_date": txn_date,
                "amount": amount,
                "description": description[:255],
                "payee": payee[:120],
                "currency": currency,
            }
        )
    return out
