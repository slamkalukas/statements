import mimetypes
import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from .. import audit, matching, storage
from ..database import get_db
from ..deps import assert_period_open, get_current_user, get_period
from ..models import Document, Period, StatementLine, User
from ..schemas import PeriodCreate, PeriodFolderUpdate, PeriodOut, SyncResult

router = APIRouter(prefix="/api/periods", tags=["periods"])

# A leading month in a filename, e.g. "05_shell.pdf" / "5-foo" / "05.invoice".
_MONTH_PREFIX = re.compile(r"^(\d{1,2})[ _.\-]")


def _file_month(name: str) -> int | None:
    m = _MONTH_PREFIX.match(name)
    if m:
        mm = int(m.group(1))
        if 1 <= mm <= 12:
            return mm
    return None


def serialize(period: Period) -> PeriodOut:
    """Build a PeriodOut with completeness computed from loaded documents and
    statement lines. `missing_count` — outgoing payments with no linked document
    — is the headline number the whole app is about."""
    docs = period.documents
    outgoing = [ln for ln in period.lines if ln.amount < 0]
    no_doc = [ln for ln in outgoing if ln.no_doc_needed]
    # "Missing" excludes both documented lines and those marked as not needing one.
    missing = [ln for ln in outgoing if ln.document_id is None and not ln.no_doc_needed]
    return PeriodOut(
        id=period.id,
        year=period.year,
        month=period.month,
        status=period.status,
        note=period.note,
        folder=period.folder_path,
        created_at=period.created_at,
        document_count=len(docs),
        has_statement=len(period.lines) > 0,
        total_size=sum(d.size_bytes for d in docs),
        outgoing_count=len(outgoing),
        missing_count=len(missing),
        no_doc_count=len(no_doc),
    )


@router.get("", response_model=list[PeriodOut])
def list_periods(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    periods = db.scalars(
        select(Period)
        .options(selectinload(Period.documents), selectinload(Period.lines))
        .order_by(Period.year.desc(), Period.month.desc())
    ).all()
    return [serialize(p) for p in periods]


@router.post("", response_model=PeriodOut, status_code=201)
def create_period(
    payload: PeriodCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    exists = db.scalar(
        select(Period.id).where(Period.year == payload.year, Period.month == payload.month)
    )
    if exists is not None:
        raise HTTPException(status_code=409, detail="That month already exists")
    period = Period(year=payload.year, month=payload.month, note=payload.note.strip())
    db.add(period)
    db.flush()
    audit.record(db, user, "create", "period", period.id, f"{payload.year}-{payload.month:02d}")
    db.commit()
    db.refresh(period)
    return serialize(period)


@router.post("/{period_id}/folder", response_model=PeriodOut)
def set_folder(
    period_id: int,
    payload: PeriodFolderUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Set this month's documents subfolder (relative to the root). A blank value
    resets to the default YYYY/MM. Only affects where *new* uploads and folder
    sync go — already-stored files keep their location and stay downloadable."""
    period = get_period(db, period_id)
    assert_period_open(period)
    try:
        norm = storage.normalize_folder(payload.folder)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid folder path")
    default = f"{period.year:04d}/{period.month:02d}"
    # Store None when it's blank or equals the default, so it stays in sync if the
    # default scheme ever changes.
    period.folder = None if (not norm or norm == default) else norm
    audit.record(db, user, "update", "period", period.id, f"folder={period.folder_path}")
    db.commit()
    db.refresh(period)
    return serialize(period)


@router.post("/{period_id}/close", response_model=PeriodOut)
def close_period(
    period_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    period = get_period(db, period_id)
    period.status = "closed"
    audit.record(db, user, "update", "period", period.id, "close")
    db.commit()
    db.refresh(period)
    return serialize(period)


@router.post("/{period_id}/reopen", response_model=PeriodOut)
def reopen_period(
    period_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    period = get_period(db, period_id)
    period.status = "open"
    audit.record(db, user, "update", "period", period.id, "reopen")
    db.commit()
    db.refresh(period)
    return serialize(period)


@router.post("/{period_id}/sync", response_model=SyncResult)
def sync_from_folder(
    period_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Scan the month's folder (and its subfolders) on disk and register any
    files not yet in the DB. New files are imported as kind='other' so they
    appear in the Documents list and can be re-typed / linked from the UI.

    The scan is recursive, so processed files filed into a subfolder (e.g.
    "hotove") are checked too. Files named with a leading month ("05_shell.pdf")
    are only picked up by that month's sync, so several months can share one
    folder; files with no month prefix are taken as-is."""
    period = get_period(db, period_id)
    assert_period_open(period)

    folder = storage.resolve_folder(period.folder_path)
    if not folder.is_dir():
        return SyncResult(scanned=0, imported=0, skipped=0)

    # Existing docs for this month, keyed by filename — so a file moved into a
    # subfolder (e.g. "hotove") updates its path instead of being duplicated.
    by_name: dict[str, Document] = {
        d.stored_path.rsplit("/", 1)[-1]: d
        for d in db.scalars(select(Document).where(Document.period_id == period_id))
    }

    # Recurse, keeping only files that belong to this month (leading-month prefix
    # matches, or no prefix at all).
    files = [
        f for f in folder.rglob("*")
        if f.is_file() and _file_month(f.name) in (None, period.month)
    ]
    new_docs: list[Document] = []
    moved = 0
    for f in files:
        rel = f.relative_to(storage.DOCUMENTS_DIR).as_posix()
        existing = by_name.get(f.name)
        if existing is not None:
            # Already tracked. If its file moved (old path gone, e.g. filed into
            # "hotove"), follow it so the link/download stays valid.
            if existing.stored_path != rel and not (storage.DOCUMENTS_DIR / existing.stored_path).exists():
                existing.stored_path = rel
                moved += 1
            continue
        mime, _ = mimetypes.guess_type(f.name)
        doc = Document(
            period_id=period_id,
            kind="other",
            original_filename=f.name,
            stored_path=rel,
            content_type=mime or "application/octet-stream",
            size_bytes=f.stat().st_size,
        )
        db.add(doc)
        new_docs.append(doc)
        by_name[f.name] = doc

    imported = len(new_docs)
    ocr_used = 0
    matched = 0
    if new_docs:
        # Read each new file's total (text layer or OCR) and pair it to a payment
        # right away, so dropping files in the folder needs no second step.
        _, ocr_used = matching.scan_documents(db, new_docs)
        matched, _ambiguous, _missing = matching.auto_pair(db, period_id)
    if new_docs or moved:
        audit.record(
            db, user, "update", "document", None,
            f"sync: {imported} new, {moved} relocated (paired {matched})",
        )
        db.commit()

    return SyncResult(
        scanned=len(files), imported=imported, skipped=len(files) - imported,
        ocr=ocr_used, matched=matched,
    )


@router.delete("/{period_id}", status_code=204)
def delete_period(
    period_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    period = get_period(db, period_id)
    has_docs = db.scalar(
        select(func.count()).select_from(Document).where(Document.period_id == period.id)
    )
    has_lines = db.scalar(
        select(func.count()).select_from(StatementLine).where(StatementLine.period_id == period.id)
    )
    if has_docs or has_lines:
        raise HTTPException(
            status_code=409,
            detail="Clear the month's documents and statement first, then remove it.",
        )
    audit.record(db, user, "delete", "period", period.id, f"{period.year}-{period.month:02d}")
    db.delete(period)
    db.commit()
