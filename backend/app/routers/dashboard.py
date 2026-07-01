from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import extract, func, select
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..deps import get_current_user
from ..models import CarTrip, Period, Travel, User
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
        return sum(
            1 for ln in p.lines
            if ln.amount < 0 and ln.document_id is None and not ln.no_doc_needed
        )

    total_missing = sum(missing(p) for p in periods)
    months_with_missing = sum(1 for p in periods if missing(p) > 0)

    # Travel trips per period
    travel_rows = db.execute(
        select(Travel.period_id, func.count(Travel.id).label("cnt"))
        .group_by(Travel.period_id)
    ).all()
    travel_counts: dict[int, int] = {row.period_id: int(row.cnt) for row in travel_rows}
    total_travels = sum(travel_counts.values())

    # Logbook drives (with km) per year+month
    car_rows = db.execute(
        select(
            extract("year", CarTrip.start_dt).label("yr"),
            extract("month", CarTrip.start_dt).label("mo"),
            func.count(CarTrip.id).label("cnt"),
        )
        .where(CarTrip.km.isnot(None))
        .group_by("yr", "mo")
    ).all()
    car_counts: dict[tuple[int, int], int] = {
        (int(row.yr), int(row.mo)): int(row.cnt) for row in car_rows
    }
    total_car_trips = sum(car_counts.values())

    now = datetime.now()
    current_year = now.year
    show_years = {current_year}
    if now.month <= 3:
        show_years.add(current_year - 1)
    recent = []
    for p in [p for p in periods if p.year in show_years]:
        po = serialize_period(p, db)
        po.travel_count = travel_counts.get(p.id, 0)
        po.car_trip_count = car_counts.get((p.year, p.month), 0)
        recent.append(po)

    return DashboardSummary(
        periods_tracked=len(periods),
        open_periods=open_periods,
        total_documents=total_documents,
        total_size=total_size,
        no_statement=no_statement,
        months_with_missing=months_with_missing,
        total_missing=total_missing,
        total_travels=total_travels,
        total_car_trips=total_car_trips,
        recent_periods=recent,
    )
