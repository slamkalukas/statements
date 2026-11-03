"""Monthly tasks: the recurring template in Settings, and each month's checklist."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit, monthly_tasks
from ..database import get_db
from ..deps import assert_period_open, get_current_user, get_period
from ..models import PeriodTask, User
from ..schemas import (
    MonthlyTaskTemplate, PeriodTaskCreate, PeriodTaskOut, PeriodTaskUpdate,
)

router = APIRouter(prefix="/api", tags=["tasks"])


@router.get("/monthly-tasks", response_model=MonthlyTaskTemplate)
def get_template(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return MonthlyTaskTemplate(titles=monthly_tasks.load_template(db))


@router.patch("/monthly-tasks", response_model=MonthlyTaskTemplate)
def update_template(
    payload: MonthlyTaskTemplate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    titles = monthly_tasks.save_template(db, payload.titles)
    audit.record(db, user, "update", "setting", None, f"monthly tasks ({len(titles)})")
    db.commit()
    return MonthlyTaskTemplate(titles=titles)


@router.get("/periods/{period_id}/tasks", response_model=list[PeriodTaskOut])
def list_tasks(
    period_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """This month's checklist, copied from the template the first time it's read."""
    return monthly_tasks.tasks_for(db, get_period(db, period_id))


@router.post("/periods/{period_id}/tasks", response_model=PeriodTaskOut, status_code=201)
def add_task(
    period_id: int,
    payload: PeriodTaskCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Add a one-off task to this month only, without touching the template."""
    period = get_period(db, period_id)
    assert_period_open(period)
    existing = monthly_tasks.tasks_for(db, period)
    task = PeriodTask(
        period_id=period.id, title=payload.title.strip(), note=payload.note.strip(),
        order_idx=max((t.order_idx for t in existing), default=-1) + 1,
    )
    db.add(task)
    db.flush()
    audit.record(db, user, "create", "period_task", task.id, task.title)
    db.commit()
    db.refresh(task)
    return task


def _get_task(db: Session, task_id: int) -> PeriodTask:
    task = db.get(PeriodTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.patch("/period-tasks/{task_id}", response_model=PeriodTaskOut)
def update_task(
    task_id: int,
    payload: PeriodTaskUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = _get_task(db, task_id)
    assert_period_open(get_period(db, task.period_id))
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(task, key, value.strip() if isinstance(value, str) else value)
    audit.record(db, user, "update", "period_task", task.id,
                 f"{task.title}: {'done' if task.done else 'open'}")
    db.commit()
    db.refresh(task)
    return task


@router.delete("/period-tasks/{task_id}", status_code=204)
def delete_task(
    task_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Drop a task from this month. The template is untouched, so the task comes
    back next month — and in this month if its list is ever rebuilt from empty."""
    task = _get_task(db, task_id)
    assert_period_open(get_period(db, task.period_id))
    audit.record(db, user, "delete", "period_task", task.id, task.title)
    db.delete(task)
    db.commit()
