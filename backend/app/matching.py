"""Shared reconciliation helpers: read amounts off documents and pair them to
outgoing payments by amount. Used by both the folder sync and the explicit
"Scan & auto-match" action so they behave identically.
"""
from collections import defaultdict
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from . import extract, storage
from .models import Document, StatementLine


def scan_documents(db: Session, docs: list[Document]) -> tuple[int, int]:
    """Read amount/date for the given documents that don't have an amount yet,
    via text layer or OCR. Sets amount/doc_date/extracted_via in place.

    Returns (scanned, ocr_used) — how many were read and how many needed OCR.
    """
    scanned = 0
    ocr_used = 0
    for d in docs:
        if d.amount is not None:
            continue
        try:
            data = storage.resolve(d.stored_path).read_bytes()
            result = extract.scan(data, d.original_filename, d.content_type)
        except Exception:
            result = extract.ScanResult(None, None, None, 0)
        scanned += 1
        if result.method == "ocr":
            ocr_used += 1
        if result.amount is not None:
            d.amount = result.amount.quantize(Decimal("0.01"))
        if result.date is not None and d.doc_date is None:
            d.doc_date = result.date
        if result.method and (result.amount is not None or result.date is not None):
            d.extracted_via = result.method
    return scanned, ocr_used


def auto_pair(db: Session, period_id: int) -> tuple[int, int, int]:
    """Pair unpaired outgoing payments to unpaired documents by amount, applied
    only where it's unambiguous (exactly one payment and one document share an
    amount). Returns (matched, ambiguous, still_missing)."""
    # The session uses autoflush=False, so make sure freshly-added documents
    # (e.g. from a folder sync) are persisted before we query them.
    db.flush()
    missing_lines = db.scalars(
        select(StatementLine).where(
            StatementLine.period_id == period_id,
            StatementLine.document_id.is_(None),
            StatementLine.amount < 0,
        )
    ).all()
    docs = db.scalars(
        select(Document)
        .where(Document.period_id == period_id, Document.kind != "bank_statement")
        .options(selectinload(Document.lines))
    ).all()
    unlinked_docs = [d for d in docs if not d.lines]

    lines_by_amount: dict[Decimal, list[StatementLine]] = defaultdict(list)
    for ln in missing_lines:
        lines_by_amount[Decimal(ln.amount)].append(ln)

    docs_by_amount: dict[Decimal, list[Document]] = defaultdict(list)
    for d in unlinked_docs:
        if d.amount is not None:
            docs_by_amount[Decimal(d.amount)].append(d)

    matched = 0
    ambiguous = 0
    for amount, lns in lines_by_amount.items():
        cands = docs_by_amount.get(-amount, [])  # doc amount positive, line negative
        if not cands:
            continue
        if len(lns) == 1 and len(cands) == 1:
            lns[0].document_id = cands[0].id
            matched += 1
        else:
            ambiguous += len(lns)

    still_missing = sum(len(lns) for lns in lines_by_amount.values()) - matched
    return matched, ambiguous, still_missing
