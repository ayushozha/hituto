"""Alembic environment — targets the app's models + DATABASE_URL.

The app still uses Base.metadata.create_all for the default SQLite dev path; Alembic owns the
Postgres + pgvector path (tech.md §7). Run with DATABASE_URL pointed at Postgres, e.g.:
    DATABASE_URL=postgresql+psycopg://hituto:hituto@localhost:5432/hituto .venv/bin/alembic upgrade head
"""
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

import app.models  # noqa: F401  — register every mapper on Base.metadata
from app.core.config import get_database_url
from app.core.db import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Prefer the app's configured DATABASE_URL over alembic.ini's placeholder.
# Use get_database_url() so postgres:// / postgresql:// become postgresql+psycopg://.
_url = get_database_url()
# ConfigParser treats % as interpolation — escape for URLs with percent-encoding.
config.set_main_option("sqlalchemy.url", _url.replace("%", "%%"))

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
