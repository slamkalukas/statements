"""Read an uploaded document (mostly PDF invoices) and pull out the figures we
need to pair it to a bank transaction: the total amount, and the document date.

Digital invoices with a selectable text layer are read directly. Scanned,
image-only PDFs (and uploaded photos/scans) fall back to OCR via Tesseract —
when the engine is available. Everything degrades gracefully: any failure
returns None rather than raising, so a weird file never blocks an upload.
"""
from __future__ import annotations

import functools
import io
import os
import re
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation

# OCR is opt-out and best-effort. It only runs when the tesseract binary and the
# Python deps are present; otherwise we silently fall back to text-layer only.
_OCR_ENABLED = os.getenv("OCR_ENABLED", "1").strip().lower() not in ("0", "false", "no")
_OCR_LANG = os.getenv("OCR_LANG", "slk+eng").strip() or "eng"
_OCR_DPI = int(os.getenv("OCR_DPI", "300"))
_OCR_MAX_PAGES = int(os.getenv("OCR_MAX_PAGES", "5"))
# Below this many characters, a PDF's text layer is treated as empty (scanned),
# so we try OCR instead.
_TEXT_LAYER_MIN_CHARS = 12

# Money tokens: "1 234,56", "1.234,56", "1,234.56", "123,45", "1234.56".
# Either grouped thousands then a 2-digit decimal, or a plain number with cents.
_MONEY_RE = re.compile(
    r"(?<!\d)\d{1,3}(?:[  .,]\d{3})+[.,]\d{2}(?![.,]?\d)"  # grouped thousands
    r"|(?<!\d)\d+[.,]\d{2}(?![.,]?\d)"                # plain, with cents
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


_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp", ".gif")


def _is_pdf(filename: str, content_type: str) -> bool:
    return content_type == "application/pdf" or filename.lower().endswith(".pdf")


def _is_text(filename: str, content_type: str) -> bool:
    return content_type.startswith("text/") or filename.lower().endswith((".txt", ".csv"))


def _is_image(filename: str, content_type: str) -> bool:
    return content_type.startswith("image/") or filename.lower().endswith(_IMAGE_EXTS)


@functools.lru_cache(maxsize=1)
def ocr_available() -> bool:
    """True when OCR is enabled and the engine + Python deps are usable."""
    if not _OCR_ENABLED:
        return False
    try:
        import pytesseract

        pytesseract.get_tesseract_version()  # raises if the binary is missing
        import pypdfium2  # noqa: F401
        from PIL import Image  # noqa: F401

        return True
    except Exception:
        return False


def _ocr_image(img) -> str:
    """OCR a PIL image, preferring the configured language but falling back to
    English if the requested language data isn't installed."""
    import pytesseract

    for lang in (_OCR_LANG, "eng"):
        try:
            return pytesseract.image_to_string(img, lang=lang)
        except Exception:
            continue
    return ""


def _ocr_image_bytes(data: bytes) -> str:
    try:
        from PIL import Image

        with Image.open(io.BytesIO(data)) as im:
            return _ocr_image(im)
    except Exception:
        return ""


def _ocr_pdf(data: bytes) -> str:
    """Render up to _OCR_MAX_PAGES pages to images and OCR each."""
    try:
        import pypdfium2 as pdfium

        out: list[str] = []
        pdf = pdfium.PdfDocument(data)
        try:
            for i in range(min(len(pdf), _OCR_MAX_PAGES)):
                page = pdf[i]
                bitmap = page.render(scale=_OCR_DPI / 72)
                pil = bitmap.to_pil()
                try:
                    out.append(_ocr_image(pil))
                finally:
                    pil.close()
        finally:
            pdf.close()
        return "\n".join(out)
    except Exception:
        return ""


def _pdf_text_layer(data: bytes) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception:
        return ""


def extract_text(data: bytes, filename: str = "", content_type: str = "") -> str:
    """Best-effort plain text from a document. Empty string if we can't read it.

    For PDFs, the embedded text layer is used when present; if it's effectively
    empty (a scanned page) and OCR is available, the pages are OCR'd instead.
    Uploaded images go straight to OCR.
    """
    if _is_pdf(filename, content_type):
        text = _pdf_text_layer(data)
        if len(text.strip()) < _TEXT_LAYER_MIN_CHARS and ocr_available():
            ocr_text = _ocr_pdf(data)
            if ocr_text.strip():
                return ocr_text
        return text
    if _is_text(filename, content_type):
        try:
            return data.decode("utf-8", errors="replace")
        except Exception:
            return ""
    if _is_image(filename, content_type) and ocr_available():
        return _ocr_image_bytes(data)
    return ""


def _norm(s: str) -> str:
    """Lowercase and strip diacritics, so keyword matching survives OCR output
    that drops Slovak accents (e.g. "úhrade" read as "uhrade")."""
    decomposed = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


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
    normalized = [_norm(ln) for ln in lines]

    for kw in _TOTAL_KEYWORDS:
        nkw = _norm(kw)
        best: Decimal | None = None
        for low, raw in zip(normalized, lines):
            if nkw in low:
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
    hints = [_norm(h) for h in _DATE_HINTS]
    for low, raw in zip((_norm(ln) for ln in text.splitlines()), text.splitlines()):
        if any(h in low for h in hints):
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
