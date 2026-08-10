import os
import sys
from pathlib import Path
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool


PROJECT_SOURCE_ROOT = Path(__file__).resolve().parents[4]

if str(PROJECT_SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_SOURCE_ROOT))

print("env.py =", Path(__file__).resolve())
print("PROJECT_SOURCE_ROOT =", PROJECT_SOURCE_ROOT)
print("sys.path =", sys.path)


from models.db_schemes.mini_rag import schemes
from models.db_schemes.mini_rag.database_url import (
    build_postgres_url,
)


SQLAlchemyBase = schemes.SQLAlchemyBase

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLAlchemyBase.metadata
database_url = build_postgres_url(os.environ)

print(
    "Loaded metadata tables:",
    sorted(target_metadata.tables.keys()),
)


def include_object(
    object_,
    name,
    type_,
    reflected,
    compare_to,
):
    """
    Ignore dynamically-created vector collection tables.

    These tables exist in PostgreSQL but are not managed
    through the application's Alembic ORM metadata.
    """

    if (
        reflected
        and type_ in {"table", "index"}
        and name.startswith("collection_")
    ):
        return False

    return True


def run_migrations_offline() -> None:
    """Run migrations in offline mode."""

    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={
            "paramstyle": "named",
        },
        include_object=include_object,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in online mode."""

    connectable = create_engine(
        database_url,
        poolclass=pool.NullPool,
    )

    try:
        with connectable.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                include_object=include_object,
                compare_type=True,
            )

            with context.begin_transaction():
                context.run_migrations()

    finally:
        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
