from sqlalchemy.orm import Session

from .models import AuditLog, User


def record(
    db: Session,
    user: User,
    action: str,
    entity_type: str,
    entity_id: int | None = None,
    detail: str = "",
) -> None:
    """Append an audit entry. Caller commits as part of the same transaction.

    Kept side-effect-light: it only adds to the session so the audit row lands
    in the same commit as the change it describes (all-or-nothing).
    """
    db.add(
        AuditLog(
            user_id=user.id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            detail=detail[:512],
        )
    )
