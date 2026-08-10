import asyncio
from uuid import uuid4

from celery_app import celery_app, get_setup_utils
from models.TaskExecutionModel import TaskExecutionModel


async def main():
    db_engine = None

    try:
        (
            db_engine,
            db_client,
            _,
            _,
            _,
            _,
            _,
            _,
        ) = await get_setup_utils()

        execution_model = await TaskExecutionModel.create_instance(
            db_client=db_client
        )

        execution = await execution_model.try_start_execution(
            idempotency_key="test-key-001",
            celery_task_id=uuid4(),
            operation="PROCESS_ASSET",
            project_id=1,
            asset_id=1,
        )

        print("First:", execution)

        execution2 = await execution_model.try_start_execution(
            idempotency_key="test-key-001",
            celery_task_id=uuid4(),
            operation="PROCESS_ASSET",
            project_id=1,
            asset_id=1,
        )

        print("Second:", execution2)

    finally:
        if db_engine is not None:
            await db_engine.dispose()


asyncio.run(main())