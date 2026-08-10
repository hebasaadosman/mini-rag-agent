import asyncio
import logging

from celery_app import (
    celery_app,
    get_db_utils,
)
from models.TaskExecutionModel import (
    TaskExecutionModel,
)


logger = logging.getLogger(__name__)


@celery_app.task(
    name="tasks.maintenance.cleanup_task_executions",
)
def cleanup_task_executions(
    success_retention_days: int = 7,
    failed_retention_days: int = 30,
):
    return asyncio.run(
        _cleanup_task_executions(
            success_retention_days=(
                success_retention_days
            ),
            failed_retention_days=(
                failed_retention_days
            ),
        )
    )


async def _cleanup_task_executions(
    *,
    success_retention_days: int,
    failed_retention_days: int,
) -> dict:
    db_engine = None

    try:
        db_engine, db_client = await get_db_utils()

        execution_model = (
            await TaskExecutionModel.create_instance(
                db_client=db_client
            )
        )

        result = (
            await execution_model.delete_old_executions(
                success_retention_days=(
                    success_retention_days
                ),
                failed_retention_days=(
                    failed_retention_days
                ),
            )
        )

        logger.info(
            "Task execution cleanup completed. "
            "deleted=%s success=%s failed=%s",
            result["deleted_count"],
            result["deleted_success"],
            result["deleted_failed"],
        )

        return result

    except Exception:
        logger.exception(
            "Task execution cleanup failed."
        )
        raise

    finally:
        if db_engine is not None:
            try:
                await db_engine.dispose()
            except Exception:
                logger.exception(
                    "Failed to dispose cleanup DB engine."
                )