import time
from collections import defaultdict, deque

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from .auth import decode_token
from .database import get_db
from .models import Period, User


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = authorization.split(" ", 1)[1].strip()
    user_id = decode_token(token)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def get_period(db: Session, period_id: int) -> Period:
    """Fetch a period or 404."""
    period = db.get(Period, period_id)
    if period is None:
        raise HTTPException(status_code=404, detail="Period not found")
    return period


def assert_period_open(period: Period) -> None:
    """Reject mutations on a closed (archived) month."""
    if period.status == "closed":
        raise HTTPException(
            status_code=409,
            detail="This month is closed. Reopen it before changing documents.",
        )


# ---- Simple in-memory rate limiting for auth endpoints ----
# Process-local sliding window keyed by client IP. Good enough to blunt
# brute-force / abuse on a single instance; swap for Redis if you scale out.
class RateLimiter:
    def __init__(self, max_requests: int, window_seconds: float):
        self.max_requests = max_requests
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def __call__(self, request: Request) -> None:
        client = request.client.host if request.client else "unknown"
        now = time.monotonic()
        hits = self._hits[client]
        while hits and now - hits[0] > self.window:
            hits.popleft()
        if len(hits) >= self.max_requests:
            raise HTTPException(
                status_code=429, detail="Too many attempts. Try again shortly."
            )
        hits.append(now)


# 10 auth attempts per IP per minute.
auth_rate_limit = RateLimiter(max_requests=10, window_seconds=60.0)
