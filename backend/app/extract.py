"""Read an uploaded document (mostly PDF invoices) and pull out the figures we
need to pair it to a bank transaction: the total amount, and the document date.

This is text-layer extraction only — digital invoices with selectable text. A
scanned image PDF yields no text here (no OCR), so it simply returns no amount
and the user pairs it manually. Everything degrades gracefully: any failure
returns None rather than raising, so a weird file never blocks an upload.
"""
from __future__ import annotations

import io
import re
from datetime import date
from decimal import Decimal, InvalidOperation

# Money tokens: "1 234,56", "1.234,56", "1,234.56", "123,45", "1234.56".
# Either grouped thousands then a 2-digit decimal, or a plain number with cents.
_MONEY_RE = re.compile(
    r"\d{1,3}(?:[  .,]\d{3})+[.,]\d{2}(?!\d)"  # with thousands separators
    r"|\d+[.,]\d{2}(?!\d)"                            # plain, with cents
)

# Keywords that mark the grand total, most-specific first. A match on an earlier
# phrase wins over a later one, so "amount due" beats a bare "total".
_TOTAL_KEYWORDS = (
    "spolu k úhrade", "suma na úhradu", "spolu na úhradu", "celkom k úhrade",
    "celková suma", "cena celkom", "k úhrade", "amount due", "total due",
    "balance due", "grand total", "total amount", "celkom", "spolu", "total",
)

# Date tokens: 24.06.2026 / 24. 6. 2026 / 2026-06-24 / 24/06/2026.
_DATE_RE = re.compile(
    r"(\d{4})-(\d{1,2})-(\d{1,2})"                       # ISO  YYYY-MM-DD
    r"|(\d{1,2})[.\-/]\s?(\d{1,2})[.\-/]\s?(\d{4})"      # DMY   DD.MM.YYYY
)
_DATE_HINTS = ("dátum vystavenia", "vystaven", "issue date", "invoice date", "dátum", "date")


def _is_pdf(filename: str, content_type: str) -> bool:
    return content_type == "application/pdf" or filename.lower().endswith(".pdf")


def _is_text(filename: str, content_type: str) -> bool:
    return content_type.startswith("text/") or filename.lower().endswith((".txt", ".csv"))


def extract_text(data: bytes, filename: str = "", content_type: str = "") -> str:
    """Best-effort plain text from a document. Empty string if we can't read it."""
    if _is_pdf(filename, content_type):
        try:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(data))
            return "\n".join((page.extract_text() or "") for page in reader.pages)
        except Exception:
            return ""
    if _is_text(filename, content_type):
        try:
            return data.decode("utf-8", errors="replace")
        except Exception:
            return ""
    return ""


def _parse_money(token: str) -> Decimal | None:
    """Parse one money token into a Decimal. The last '.' or ',' is the decimal
    separator (we only match tokens with exactly two trailing digits); any other
    separators are thousands grouping and are dropped."""
    t = token.replace(" ", "").replace(" ", "")
    cut = max(t.rfind("."), t.rfind(","))
    if cut == -1:
        return None
    intpart = re.sub(r"[.,]", "", t[:cut]) or "0"
    decpart = t[cut + 1:]
    try:
        return Decimal(f"{intpart}.{decpart}")
    except InvalidOperation:
        return None


def extract_amount(text: str) -> Decimal | None:
    """The document's total. Prefers an amount sitting on a line that names a
    total ("k úhrade", "total", ...); otherwise falls back to the largest amount
    in the document, which for an invoice is almost always the grand total."""
    if not text:
        return None
    lines = text.splitlines()
    lowered = [ln.lower() for ln in lines]

    for kw in _TOTAL_KEYWORDS:
        best: Decimal | None = None
        for low, raw in zip(lowered, lines):
            if kw in low:
                for tok in _MONEY_RE.findall(raw):
                    val = _parse_money(tok)
                    if val is not None and (best is None or val > best):
                        best = val
        if best is not None:
            return best

    # Fallback: the largest money figure anywhere.
    best = None
    for tok in _MONEY_RE.findall(text):
        val = _parse_money(tok)
        if val is not None and (best is None or val > best):
            best = val
    return best


def _parse_date_match(m: re.Match) -> date | None:
    try:
        if m.group(1):  # ISO
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        else:           # DMY
            d, mo, y = int(m.group(4)), int(m.group(5)), int(m.group(6))
        return date(y, mo, d)
    except (ValueError, TypeError):
        return None


def extract_date(text: str) -> date | None:
    """A plausible document date. Prefers a date on a line that mentions an
    issue/invoice date; otherwise the first date found."""
    if not text:
        return None
    for low, raw in zip((ln.lower() for ln in text.splitlines()), text.splitlines()):
        if any(h in low for h in _DATE_HINTS):
            m = _DATE_RE.search(raw)
            if m:
                d = _parse_date_match(m)
                if d:
                    return d
    m = _DATE_RE.search(text)
    return _parse_date_match(m) if m else None


def scan_document(
    data: bytes, filename: str = "", content_type: str = ""
) -> tuple[Decimal | None, date | None]:
    """Extract (amount, date) from a document. Either may be None."""
    text = extract_text(data, filename, content_type)
    return extract_amount(text), extract_date(text)
