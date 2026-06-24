from decimal import Decimal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .. import audit, storage
from ..database import get_db
from ..deps import assert_period_open, get_current_user, get_period
from ..models import Document, StatementLine, User
from ..schemas import LinkRequest, StatementImportResult, StatementLineOut
from ..statements import parse_statement

router = APIRouter(prefix="/api", tags=["reconcile"])

# Cap on a parsed statement, so a malformed/huge file can't flood the table.
MAX_LINES = 10_000


def serialize(line: StatementLine) -> StatementLineOut:
    return StatementLineOut(
        id=line.id,
        period_id=line.period_id,
        txn_date=line.txn_date,
        amount=float(line.amount),
        description=line.description,
        payee=line.payee,
        currency=line.currency,
        document_id=line.document_id,
        document_filename=line.document.original_filename if line.document else None,
    )


@router.get("/periods/{period_id}/lines", response_model=list[StatementLineOut])
def list_lines(
    period_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    get_period(db, period_id)
    lines = db.scalars(
        select(StatementLine)
        .where(StatementLine.period_id == period_id)
        .options(selectinload(StatementLine.document))
        .order_by(StatementLine.txn_date, StatementLine.id)
    ).all()
    return [serialize(ln) for ln in lines]


@router.post("/periods/{period_id}/statement", response_model=StatementImportResult)
async def import_statement(
    period_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Upload the month's bank statement: store the file (as a bank_statement
    document) and parse its transactions into reconciliation lines.

    Re-import is safe — lines that duplicate an existing one (same date + amount
    + description) are skipped, so the missing report doesn't double-count.
    """
    period = get_period(db, period_id)
    assert_period_open(period)

    raw = await file.read()
    try:
        rows, fmt = parse_statement(raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Could not parse statement: {exc}")
    if not rows:
        raise HTTPException(status_code=400, detail="No transactions found in the statement")
    if len(rows) > MAX_LINES:
        raise HTTPException(status_code=413, detail=f"Too many transactions (limit {MAX_LINES})")

    # Existing (date, amount, description) keys so re-imports don't pile up.
    seen: set[tuple] = set()
    for d, a, desc in db.execute(
        select(StatementLine.txn_date, StatementLine.amount, StatementLine.description).where(
            StatementLine.period_id == period.id
        )
    ).all():
        seen.add((d, Decimal(a), desc))

    imported = 0
    duplicates = 0
    outgoing = 0
    for r in rows:
        key = (r["txn_date"], r["amount"], r["description"])
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        db.add(
            StatementLine(
                period_id=period.id,
                txn_date=r["txn_date"],
                amount=r["amount"],
                description=r["description"],
                payee=r["payee"],
                currency=r["currency"],
            )
        )
        imported += 1
        if r["amount"] < 0:
            outgoing += 1

    # Also keep the original statement file alongside the documents.
    try:
        # Rewind so we can persist the bytes we already read.
        rel_path, size, original = storage.save_upload_bytes(
            period.year, period.month, file.filename or "statement", raw
        )
        db.add(
            Document(
                period_id=period.id,
                kind="bank_statement",
                original_filename=(file.filename or "statement")[:255],
                stored_path=rel_path,
                content_type=file.content_type or "",
                size_bytes=size,
                note=f"Imported statement ({fmt})",
            )
        )
    except storage.UploadTooLarge:
        raise HTTPException(
            status_code=413, detail=f"File too large (limit {storage.MAX_UPLOAD_MB} MB)"
        )

    audit.record(
        db, user, "create", "statement", period.id,
        f"{fmt}: {imported} lines ({duplicates} dup)",
    )
    db.commit()
    return StatementImportResult(
        format=fmt, parsed=len(rows), imported=imported, duplicates=duplicates, outgoing=outgoing
    )


@router.post("/lines/{line_id}/link", response_model=StatementLineOut)
def link_document(
    line_id: int,
    payload: LinkRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Attach a document to a statement line (confirm a match)."""
    line = db.get(StatementLine, line_id)
    if line is None:
        raise HTTPException(status_code=404, detail="Statement line not found")
    assert_period_open(get_period(db, line.period_id))

    doc = db.get(Document, payload.document_id)
    if doc is None or doc.period_id != line.period_id:
        raise HTTPException(status_code=404, detail="Document not found in this month")

    line.document_id = doc.id
    audit.record(db, user, "update", "statement_line", line.id, f"link doc {doc.id}")
    db.commit()
    db.refresh(line)
    return serialize(line)


@router.post("/lines/{line_id}/unlink", response_model=StatementLineOut)
def unlink_document(
    line_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    line = db.get(StatementLine, line_id)
    if line is None:
        raise HTTPException(status_code=404, detail="Statement line not found")
    assert_period_open(get_period(db, line.period_id))
    line.document_id = None
    audit.record(db, user, "update", "statement_line", line.id, "unlink")
    db.commit()
    db.refresh(line)
    return serialize(line)


@router.delete("/lines/{line_id}", status_code=204)
def delete_line(
    line_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Remove a single parsed line (e.g. a junk row you don't want to track)."""
    line = db.get(StatementLine, line_id)
    if line is None:
        raise HTTPException(status_code=404, detail="Statement line not found")
    assert_period_open(get_period(db, line.period_id))
    audit.record(db, user, "delete", "statement_line", line.id)
    db.delete(line)
    db.commit()


@router.delete("/periods/{period_id}/lines", status_code=204)
def clear_lines(
    period_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Clear all parsed lines for a month (e.g. to re-import a corrected file).
    Leaves uploaded documents in place."""
    period = get_period(db, period_id)
    assert_period_open(period)
    for line in db.scalars(
        select(StatementLine).where(StatementLine.period_id == period_id)
    ).all():
        db.delete(line)
    audit.record(db, user, "delete", "statement", period_id, "clear lines")
    db.commit()
