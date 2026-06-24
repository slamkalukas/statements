"""Test harness: an isolated in-memory SQLite DB per test and a temp documents
directory, wired into the app via dependency overrides. The admin user is seeded
fresh per test; rate limiting is disabled here (tested separately).
"""
import importlib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "changeme123"


@pytest.fixture()
def storage(tmp_path, monkeypatch):
    """Point DOCUMENTS_DIR at a temp dir and reload the storage module so its
    module-level path constant picks it up."""
    monkeypatch.setenv("DOCUMENTS_DIR", str(tmp_path / "documents"))
    monkeypatch.setenv("MAX_UPLOAD_MB", "1")
    import app.storage as storage_module

    importlib.reload(storage_module)
    storage_module.ensure_root()
    return storage_module


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    import app.models  # noqa: F401  (registers all tables on Base)
    from app.database import Base

    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    try:
        yield TestingSessionLocal
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture()
def client(db_session, storage, monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", ADMIN_EMAIL)
    monkeypatch.setenv("ADMIN_PASSWORD", ADMIN_PASSWORD)

    # Reload modules that read env / storage at import time so overrides apply.
    import app.seed as seed_module
    import app.routers.documents as documents_module

    importlib.reload(seed_module)
    importlib.reload(documents_module)

    from app.database import get_db
    from app.deps import auth_rate_limit
    from app.main import app

    def override_get_db():
        db = db_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[auth_rate_limit] = lambda: None

    # Seed the admin user into the test DB.
    with db_session() as db:
        seed_module.seed(db)

    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
def auth_headers(client):
    res = client.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['token']}"}
