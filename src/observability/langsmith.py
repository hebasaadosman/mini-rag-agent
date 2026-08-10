import os

from helpers.config import Settings


def get_langsmith_project_name(
    settings: Settings,
) -> str:
    """Return an environment-specific LangSmith project name."""
    base_name = settings.LANGSMITH_PROJECT.strip()
    environment = settings.APP_ENV.strip().lower()

    if not base_name:
        raise ValueError("LANGSMITH_PROJECT must not be empty.")

    if not environment:
        raise ValueError("APP_ENV must not be empty.")

    suffix = f"-{environment}"
    if base_name.lower().endswith(suffix):
        return base_name

    return f"{base_name}{suffix}"


def configure_langsmith(
    settings: Settings,
) -> None:
    """
    Configure LangSmith tracing.

    Safe to call multiple times.
    """

    if not settings.LANGSMITH_TRACING:
        return

    os.environ.setdefault(
        "LANGSMITH_TRACING",
        str(settings.LANGSMITH_TRACING).lower(),
    )

    os.environ.setdefault(
        "LANGSMITH_API_KEY",
        settings.LANGSMITH_API_KEY,
    )

    # Override the raw value loaded from the environment with
    # the resolved name so local and production traces cannot
    # accidentally share the same LangSmith project.
    os.environ["LANGSMITH_PROJECT"] = (
        get_langsmith_project_name(settings)
    )
