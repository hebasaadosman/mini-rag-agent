from contextlib import asynccontextmanager
from typing import AsyncGenerator

from langgraph.checkpoint.postgres.aio import (
    AsyncPostgresSaver,
)

from helpers.config import Settings


@asynccontextmanager
async def create_postgres_checkpointer(
    settings: Settings,
) -> AsyncGenerator[
    AsyncPostgresSaver,
    None,
]:
    """
    Create a persistent PostgreSQL-backed
    LangGraph checkpointer.

    This connection is independent from the
    application's SQLAlchemy/asyncpg connection.
    """

    connection_string = (
        "postgresql://"
        f"{settings.POSTGRES_USER}:"
        f"{settings.POSTGRES_PASSWORD}@"
        f"{settings.POSTGRES_HOST}:"
        f"{settings.POSTGRES_PORT}/"
        f"{settings.POSTGRES_DB}"
    )

    async with (
        AsyncPostgresSaver.from_conn_string(
            connection_string
        )
    ) as checkpointer:
        await checkpointer.setup()

        yield checkpointer