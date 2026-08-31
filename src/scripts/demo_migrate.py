"""Fail-fast Alembic upgrade for the isolated demo database."""
from alembic import command
from alembic.config import Config


def main() -> None:
    config = Config("/app/models/db_schemes/mini_rag/alembic.ini")
    command.upgrade(config, "head")


if __name__ == "__main__":
    main()
