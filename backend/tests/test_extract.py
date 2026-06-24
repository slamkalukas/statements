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


def test_dotted_date_is_not_read_as_amount():
    # 24.06.2026 must not be mistaken for the amount 24.06.
    assert extract.extract_amount("Datum 24.06.2026") is None
    assert extract.extract_amount("Datum 24.06.2026\nSpolu k uhrade 150,00") == Decimal("150.00")


def test_keyword_matches_without_diacritics():
    # OCR often drops Slovak accents — "uhrade" must still match "úhrade".
    text = "Medzisucet 100,00\nSpolu k uhrade 120,00 EUR"
    assert extract.extract_amount(text) == Decimal("120.00")


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


def test_scan_reports_text_method_for_text_file():
    r = extract.scan(b"Spolu k uhrade 12,00 EUR", "bill.txt", "text/plain")
    assert r.amount == Decimal("12.00")
    assert r.method == "text"
    assert r.chars > 0


def test_scan_reports_no_method_when_unreadable():
    r = extract.scan(b"not a pdf", "x.pdf", "application/pdf")
    assert r.method is None and r.amount is None


def _make_text_image(text: str) -> bytes:
    """A clear, high-contrast PNG with `text` rendered large — OCR-friendly."""
    PIL = pytest.importorskip("PIL")  # noqa: F841
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (900, 160), "white")
    draw = ImageDraw.Draw(img)
    font = None
    for path in ("DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        try:
            font = ImageFont.truetype(path, 48)
            break
        except Exception:
            continue
    draw.text((20, 50), text, fill="black", font=font or ImageFont.load_default())
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_ocr_reads_amount_from_image():
    if not extract.ocr_available():
        pytest.skip("Tesseract OCR engine not installed in this environment")
    data = _make_text_image("Spolu k uhrade 88,80 EUR")
    amount, _ = extract.scan_document(data, "scan.png", "image/png")
    assert amount == Decimal("88.80")


def test_image_returns_none_without_ocr():
    # When OCR isn't available, an image simply yields no amount (manual pairing).
    if extract.ocr_available():
        pytest.skip("OCR available; this checks the no-OCR fallback")
    amount, doc_date = extract.scan_document(b"\x89PNG fake", "x.png", "image/png")
    assert amount is None and doc_date is None
