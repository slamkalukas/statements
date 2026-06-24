from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..deps import get_current_user
from ..models import Period, User
from ..schemas import DashboardSummary
from .periods import serialize as serialize_period

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardSummary)
def summary(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    periods = db.scalars(
        select(Period)
        .options(selectinload(Period.documents), selectinload(Period.lines))
        .order_by(Period.year.desc(), Period.month.desc())
    ).all()

    total_documents = sum(len(p.documents) for p in periods)
    total_size = sum(d.size_bytes for p in periods for d in p.documents)
    open_periods = sum(1 for p in periods if p.status == "open")
    no_statement = sum(1 for p in periods if len(p.lines) == 0)

    def missing(p: Period) -> int:
        return sum(1 for ln in p.lines if ln.amount < 0 and ln.document_id is None)

    total_missing = sum(missing(p) for p in periods)
    months_with_missing = sum(1 for p in periods if missing(p) > 0)

    return DashboardSummary(
        periods_tracked=len(periods),
        open_periods=open_periods,
        total_documents=total_documents,
        total_size=total_size,
        no_statement=no_statement,
        months_with_missing=months_with_missing,
        total_missing=total_missing,
        recent_periods=[serialize_period(p) for p in periods[:6]],
    )
