"""
Alembic env.py — FORESIGHT database migration environment.

Reads DATABASE_URL_SYNC from environment (never from alembic.ini).
Supports both online mode (connected DB) and offline mode (SQL scripts).
"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Add project root to path so we can import from 'common'
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from infrastructure.db.base import Base  # noqa: E402 — import after path fix

# Alembic Config object provides access to alembic.ini values
config = context.config

# Override sqlalchemy.url from environment variable — never hardcode credentials
database_url = os.environ.get("DATABASE_URL_SYNC")
if not database_url:
    raise RuntimeError(
        "DATABASE_URL_SYNC environment variable is not set. "
        "Copy .env.template to .env and fill in PostgreSQL credentials."
    )
config.set_main_option("sqlalchemy.url", database_url)

# Set up Python logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Metadata for autogenerate support
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode — generates SQL scripts without
    requiring a live database connection. Useful for auditing / production review.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode — directly applies to the connected database.
    Uses NullPool to avoid connection leaks in migration context.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
