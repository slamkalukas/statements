import logging
import os
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

logger = logging.getLogger("statements.auth")

ALGORITHM = "HS256"
TOKEN_TTL_DAYS = 30

ENV = os.getenv("ENV", "development").lower()
# Secrets we refuse to run with in production.
_WEAK_SECRETS = {"", "change-me-in-production", "change-me", "secret"}


def _resolve_secret_key() -> str:
    """Resolve the JWT signing key, refusing to start insecurely in production.

    - production: a strong, non-default SECRET_KEY is mandatory. We fail fast
      rather than silently signing tokens with a guessable key.
    - development: if no real key is set we generate an ephemeral random one so
      the app still boots; tokens simply don't survive a restart.
    """
    key = os.getenv("SECRET_KEY", "").strip()
    if ENV == "production":
        if key in _WEAK_SECRETS or len(key) < 32:
            raise RuntimeError(
                "SECRET_KEY must be set to a strong (>=32 char) random value "
                "when ENV=production. Refusing to start with a default/weak key."
            )
        return key
    if key in _WEAK_SECRETS:
        logger.warning(
            "No strong SECRET_KEY set; generating an ephemeral development key. "
            "Sessions will be invalidated on restart. Set SECRET_KEY for stable tokens."
        )
        return secrets.token_urlsafe(48)
    return key


SECRET_KEY = _resolve_secret_key()


# ---- Password hashing (bcrypt) ----
# bcrypt operates on at most 72 bytes; longer inputs are truncated by the
# algorithm. We truncate explicitly so newer bcrypt builds don't raise.
def _to_bcrypt_bytes(password: str) -> bytes:
    return password.encode("utf-8")[:72]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_to_bcrypt_bytes(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(_to_bcrypt_bytes(password), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ---- JWT session tokens ----
def create_token(user_id: int) -> str:
    payload = {
        "sub": str(user_id),
        "exp": datetime.now(timezone.utc) + timedelta(days=TOKEN_TTL_DAYS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> int | None:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return int(payload["sub"])
    except Exception:
        return None
