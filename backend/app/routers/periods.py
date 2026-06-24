from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from .. import audit
from ..database import get_db
from ..deps import get_current_user, get_period
from ..models import Document, Period, StatementLine, User
from ..schemas import PeriodCreate, PeriodOut

router = APIRouter(prefix="/api/periods", tags=["periods"])


def serialize(period: Period) -> PeriodOut:
    """Build a PeriodOut with completeness computed from loaded documents and
    statement lines. `missing_count` — outgoing payments with no linked document
    — is the headline number the whole app is about."""
    docs = period.documents
    outgoing = [ln for ln in period.lines if ln.amount < 0]
    missing = [ln for ln in outgoing if ln.document_id is None]
    return PeriodOut(
        id=period.id,
        year=period.year,
        month=period.month,
        status=period.status,
        note=period.note,
        created_at=period.created_at,
        document_count=len(docs),
        has_statement=len(period.lines) > 0,
        total_size=sum(d.size_bytes for d in docs),
        outgoing_count=len(outgoing),
        missing_count=len(missing),
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
