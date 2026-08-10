from collections.abc import Mapping

from sqlalchemy.engine import URL


POSTGRES_ENVIRONMENT_VARIABLES = (
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
)


def build_postgres_url(
    environment: Mapping[str, str],
) -> URL:
    """Build a safe SQLAlchemy URL from the container environment."""

    missing = [
        variable
        for variable in POSTGRES_ENVIRONMENT_VARIABLES
        if not environment.get(variable)
    ]

    if missing:
        raise RuntimeError(
            "Missing PostgreSQL environment variables: "
            + ", ".join(missing)
        )

    try:
        port = int(environment["POSTGRES_PORT"])
    except ValueError as exc:
        raise RuntimeError(
            "POSTGRES_PORT must be an integer."
        ) from exc

    return URL.create(
        drivername="postgresql+psycopg2",
        username=environment["POSTGRES_USER"],
        password=environment["POSTGRES_PASSWORD"],
        host=environment["POSTGRES_HOST"],
        port=port,
        database=environment["POSTGRES_DB"],
    )
