"""Alembic migration environment.

Reads the database URL from DATABASE_URL (falling back to the app default) and
targets the SQLAlchemy metadata declared on the application's models, so
autogenerate stays in sync with the ORM.
"""
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make the app package importable when alembic runs from backend/.
from app import models  # noqa: F401  (ensures all tables register on Base)
from app.database import DATABASE_URL, Base

config = context.config
config.set_main_option("sqlalchemy.url", os.getenv("DATABASE_URL", DATABASE_URL))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
