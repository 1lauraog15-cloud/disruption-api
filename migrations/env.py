"""Alembic environment: reads DATABASE_URL and the models' metadata."""

import os

from alembic import context
from sqlalchemy import create_engine

from disruption_api.models import Base

config = context.config
target_metadata = Base.metadata


def _url() -> str:
    return os.environ.get("DATABASE_URL") or config.get_main_option("sqlalchemy.url") or "sqlite:///disruption.db"


def run_migrations_offline() -> None:
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        _run(connection)
        return
    with create_engine(_url()).connect() as connection:
        _run(connection)


def _run(connection) -> None:  # type: ignore[no-untyped-def]
    context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
