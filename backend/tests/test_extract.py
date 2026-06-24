"""Amount/date extraction from document text, plus end-to-end PDF scanning."""
import io
from datetime import date
from decimal import Decimal

import pytest

from app import extract


def test_amount_prefers_total_keyword():
    text = "Položka A 10,00\nDPH 20% 2,00\nSpolu k úhrade 12,00 EUR"
    assert extract.extract_amount(text) == Decimal("12.00")


def test_amount_handles_thousands_separators():
    assert extract.extract_amount("Total: 1 234,56 €") == Decimal("1234.56")
    assert extract.extract_amount("Total: 1.234,56 €") == Decimal("1234.56")
    assert extract.extract_amount("Total: 1,234.56") == Decimal("1234.56")


def test_amount_falls_back_to_largest():
    # No keyword — the grand total is the largest figure on an invoice.
    text = "Item one 5,00\nItem two 7,50\nNett 12,50"
    assert extract.extract_amount(text) == Decimal("12.50")


def test_amount_none_when_no_money():
    assert extract.extract_amount("no figures here") is None
    assert extract.extract_amount("") is None


def test_date_prefers_issue_hint():
    text = "Splatnosť 30.07.2026\nDátum vystavenia 24.06.2026"
    assert extract.extract_date(text) == date(2026, 6, 24)


def test_date_iso_and_dmy():
    assert extract.extract_date("Booked 2026-06-24") == date(2026, 6, 24)
    assert extract.extract_date("Date 24.06.2026") == date(2026, 6, 24)


def _make_pdf(text: str) -> bytes:
    """Build a one-page PDF carrying `text` as a real text layer."""
    pypdf = pytest.importorskip("pypdf")
    rl = pytest.importorskip("reportlab.pdfgen.canvas")  # noqa: F841
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    y = 800
    for line in text.splitlines():
        c.drawString(40, y, line)
        y -= 20
    c.save()
    return buf.getvalue()


def test_scan_pdf_text_layer():
    pytest.importorskip("reportlab")
    data = _make_pdf("Faktura\nDatum vystavenia 24.06.2026\nSpolu k uhrade 99,90 EUR")
    amount, doc_date = extract.scan_document(data, "invoice.pdf", "application/pdf")
    assert amount == Decimal("99.90")
    assert doc_date == date(2026, 6, 24)


def test_scan_unreadable_pdf_returns_none():
    # Not a real PDF — extraction must degrade to (None, None), never raise.
    amount, doc_date = extract.scan_document(b"not a pdf", "x.pdf", "application/pdf")
    assert amount is None and doc_date is None
