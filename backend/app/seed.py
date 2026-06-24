"""Bootstrap the single admin user. Runs on startup; only acts on an empty
users table, so an existing password is never overwritten."""
import logging
import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import hash_password
from .models import User

logger = logging.getLogger("statements.seed")

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@example.com")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "changeme")


def seed(db: Session) -> None:
    if db.scalar(select(User).limit(1)) is not None:
        return  # admin already exists

    db.add(
        User(email=ADMIN_EMAIL.strip().lower(), password_hash=hash_password(ADMIN_PASSWORD))
    )
    db.commit()
    logger.info("Created admin user %s", ADMIN_EMAIL)
