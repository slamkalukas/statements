import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from . import auth, storage
from .database import Base, SessionLocal, engine
from .routers import auth as auth_router
from .routers import dashboard, documents, periods, reconcile
from .seed import seed

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("statements.request")


def _init_db(retries: int = 10, delay: float = 2.0) -> None:
    """Wait for the database to accept connections, then bootstrap.

    In development we create tables and seed the admin user for a zero-config
    `docker compose up`. In production we do neither — schema is owned by
    Alembic migrations (`alembic upgrade head`) and the admin is seeded on first
    boot only if the users table is empty.
    """
    last_err = None
    for _ in range(retries):
        try:
            with SessionLocal() as db:
                db.execute(text("SELECT 1"))
                if auth.ENV != "production":
                    Base.metadata.create_all(bind=engine)
                seed(db)  # idempotent; safe in every environment
            return
        except OperationalError as exc:  # db not ready yet
            last_err = exc
            time.sleep(delay)
    if last_err:
        raise last_err


@asynccontextmanager
async def lifespan(app: FastAPI):
    storage.ensure_root()  # make sure the mapped documents folder exists
    _init_db()
    yield


app = FastAPI(title="Statements API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "%s %s -> %s (%.1fms)",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )
    return response


@app.get("/api/health")
def health():
    """Liveness + DB connectivity check."""
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "ok"}
    except SQLAlchemyError:
        return {"status": "degraded", "database": "unavailable"}


app.include_router(auth_router.router)
app.include_router(periods.router)
app.include_router(documents.router)
app.include_router(reconcile.router)
app.include_router(dashboard.router)
