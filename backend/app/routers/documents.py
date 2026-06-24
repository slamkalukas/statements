from datetime import date
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .. import audit, extract, storage
from ..database import get_db
from ..deps import assert_period_open, get_current_user, get_period
from ..models import Document, StatementLine, User
from ..schemas import DOCUMENT_KINDS, DocumentOut

router = APIRouter(prefix="/api", tags=["documents"])


def serialize(d: Document) -> DocumentOut:
    return DocumentOut(
        id=d.id,
        period_id=d.period_id,
        kind=d.kind,
        original_filename=d.original_filename,
        content_type=d.content_type,
        size_bytes=d.size_bytes,
        doc_date=d.doc_date,
        amount=float(d.amount) if d.amount is not None else None,
        note=d.note,
        uploaded_at=d.uploaded_at,
        linked_line_count=len(d.lines),
    )


def _parse_optional_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=400, detail="doc_date must be YYYY-MM-DD")


def _parse_optional_amount(value: str | None) -> Decimal | None:
    if value is None or value.strip() == "":
        return None
    try:
        return Decimal(value).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        raise HTTPException(status_code=400, detail="amount is not a valid number")


@router.get("/periods/{period_id}/documents", response_model=list[DocumentOut])
def list_documents(
    period_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    get_period(db, period_id)  # 404 if missing
    docs = db.scalars(
        select(Document)
        .where(Document.period_id == period_id)
        .options(selectinload(Document.lines))
        .order_by(Document.kind, Document.uploaded_at.desc())
    ).all()
    return [serialize(d) for d in docs]


@router.post("/periods/{period_id}/documents", response_model=DocumentOut, status_code=201)
def upload_document(
    period_id: int,
    file: UploadFile = File(...),
    kind: str = Form(...),
    note: str = Form(""),
    doc_date: str | None = Form(None),
    amount: str | None = Form(None),
    line_id: int | None = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    period = get_period(db, period_id)
    assert_period_open(period)
    if kind not in DOCUMENT_KINDS:
        raise HTTPException(status_code=400, detail=f"kind must be one of {DOCUMENT_KINDS}")

    # Optional: attach the new document to a statement line in one step.
    line = None
    if line_id is not None:
        line = db.get(StatementLine, line_id)
        if line is None or line.period_id != period.id:
            raise HTTPException(status_code=404, detail="Statement line not found in this month")

    parsed_date = _parse_optional_date(doc_date)
    parsed_amount = _parse_optional_amount(amount)

    try:
        rel_path, size, original = storage.save_upload(period.year, period.month, file)
    except storage.UploadTooLarge:
        raise HTTPException(
            status_code=413, detail=f"File too large (limit {storage.MAX_UPLOAD_MB} MB)"
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid file path")

    # Scan the file (PDF/text) for its total and date when not given by hand, so
    # uploaded invoices can be paired to a transaction without manual data entry.
    if parsed_amount is None or parsed_date is None:
        try:
            data = storage.resolve(rel_path).read_bytes()
            scanned_amount, scanned_date = extract.scan_document(
                data, original, file.content_type or ""
            )
            if parsed_amount is None and scanned_amount is not None:
                parsed_amount = scanned_amount.quantize(Decimal("0.01"))
            if parsed_date is None and scanned_date is not None:
                parsed_date = scanned_date
        except Exception:
            pass  # extraction is best-effort; never block an upload

    doc = Document(
        period_id=period.id,
        kind=kind,
        original_filename=original[:255],
        stored_path=rel_path,
        content_type=file.content_type or "",
        size_bytes=size,
        doc_date=parsed_date,
        amount=parsed_amount,
        note=note.strip()[:512],
    )
    db.add(doc)
    db.flush()
    if line is not None:
        line.document_id = doc.id  # link on upload (the "attach to this payment" flow)
    elif doc.amount is not None and kind != "bank_statement":
        # No explicit target: auto-pair to an outgoing payment of the same amount,
        # but only when exactly one such payment is still missing a document.
        matches = db.scalars(
            select(StatementLine).where(
                StatementLine.period_id == period.id,
                StatementLine.document_id.is_(None),
                StatementLine.amount == -doc.amount,
            )
        ).all()
        if len(matches) == 1:
            matches[0].document_id = doc.id
    audit.record(db, user, "create", "document", doc.id, f"{kind}: {original}")
    db.commit()
    db.refresh(doc)
    return serialize(doc)


@router.get("/documents/{document_id}/download")
def download_document(
    document_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    path = storage.resolve(doc.stored_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="File missing on disk")
    return FileResponse(
        path,
        media_type=doc.content_type or "application/octet-stream",
        filename=doc.original_filename,
    )


@router.delete("/documents/{document_id}", status_code=204)
def delete_document(
    document_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    assert_period_open(get_period(db, doc.period_id))

    # Detach from any statement lines first so they revert to "missing".
    for line in db.scalars(
        select(StatementLine).where(StatementLine.document_id == doc.id)
    ).all():
        line.document_id = None

    storage.delete(doc.stored_path)
    audit.record(db, user, "delete", "document", doc.id, f"{doc.kind}: {doc.original_filename}")
    db.delete(doc)
    db.commit()
