"""Recurring monthly tasks: a template kept in settings, copied into each month.

The template is the list of things that come round every month (file the VAT
return, pay salaries, reconcile the card). A month materialises its own copy the
first time its list is read, so ticking one off is per month and editing the
template later does not rewrite a month already filed.
"""
import json
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Period, PeriodTask, Setting

logger = logging.getLogger(__name__)

TEMPLATE_KEY = "monthly_tasks"
MAX_TITLE = 200


def load_template(db: Session) -> list[str]:
    """The task titles that recur every month, in display order."""
    row = db.scalar(select(Setting).where(Setting.key == TEMPLATE_KEY))
    if not row or not row.value.strip():
        return []
    try:
        data = json.loads(row.value)
    except ValueError:
        logger.warning("monthly task template is not valid JSON, ignoring it")
        return []
    return [str(t).strip()[:MAX_TITLE] for t in data if str(t).strip()]


def save_template(db: Session, titles: list[str]) -> list[str]:
    """Replace the template. Blank entries are dropped, duplicates collapse."""
    clean: list[str] = []
    for title in titles:
        t = str(title).strip()[:MAX_TITLE]
        if t and t not in clean:
            clean.append(t)
    payload = json.dumps(clean, ensure_ascii=False)
    row = db.scalar(select(Setting).where(Setting.key == TEMPLATE_KEY))
    if row:
        row.value = payload
    else:
        db.add(Setting(key=TEMPLATE_KEY, value=payload))
    return clean


def tasks_for(db: Session, period: Period) -> list[PeriodTask]:
    """This month's tasks, materialising the template on first read.

    Only an open month materialises: a closed month that never had tasks stays
    empty rather than gaining a checklist after the fact.
    """
    existing = db.scalars(
        select(PeriodTask).where(PeriodTask.period_id == period.id).order_by(PeriodTask.order_idx)
    ).all()
    if existing or period.status != "open":
        return list(existing)

    created = [
        PeriodTask(period_id=period.id, title=title, order_idx=i)
        for i, title in enumerate(load_template(db))
    ]
    if not created:
        return []
    db.add_all(created)
    db.commit()
    for t in created:
        db.refresh(t)
    return created
