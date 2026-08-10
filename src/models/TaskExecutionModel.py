from sqlalchemy import func, select, text, update,delete
from sqlalchemy.dialects.postgresql import insert

from .BaseDataModel import BaseDataModel
from .db_schemes.mini_rag.schemes.task_execution import (
    TaskExecution,
)
from datetime import datetime, timedelta, timezone


EXECUTION_LEASE_INTERVAL = text("INTERVAL '5 minutes'")


class TaskExecutionModel(BaseDataModel):
    def __init__(self, db_client):
        super().__init__(db_client)
        self.collection = self.db_client

    @classmethod
    async def create_instance(
        cls,
        db_client: object,
    ):
        return cls(db_client)

    async def try_start_execution(
        self,
        *,
        idempotency_key: str,
        celery_task_id,
        operation: str,
        project_id: int,
        asset_id: int | None = None,
    ) -> TaskExecution | None:
        """
        Atomically creates and claims a new RUNNING execution.

        Returns:
            TaskExecution:
                This worker successfully claimed the execution.

            None:
                An execution with the same idempotency key
                already exists.
        """

        statement = (
            insert(TaskExecution)
            .values(
                idempotency_key=idempotency_key,
                celery_task_id=celery_task_id,
                operation=operation,
                project_id=project_id,
                asset_id=asset_id,
                status="RUNNING",
                heartbeat_at=func.now(),
                lease_expires_at=(
                    func.now() + EXECUTION_LEASE_INTERVAL
                ),
                attempt_count=1,
                error_message=None,
                result=None,
                finished_at=None,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    TaskExecution.idempotency_key
                ]
            )
            .returning(TaskExecution)
        )

        async with self.db_client() as session:
            async with session.begin():
                result = await session.execute(statement)
                execution = result.scalar_one_or_none()

            return execution

    async def get_by_idempotency_key(
        self,
        idempotency_key: str,
    ) -> TaskExecution | None:
        statement = select(TaskExecution).where(
            TaskExecution.idempotency_key
            == idempotency_key
        )

        async with self.db_client() as session:
            result = await session.execute(statement)
            return result.scalar_one_or_none()

    async def mark_success(
        self,
        execution_id: int,
        result_data: dict,
    ) -> TaskExecution | None:
        """
        Marks an owned execution as successfully completed.
        """

        statement = (
            update(TaskExecution)
            .where(
                TaskExecution.execution_id
                == execution_id,
                TaskExecution.status == "RUNNING",
            )
            .values(
                status="SUCCESS",
                result=result_data,
                error_message=None,
                finished_at=func.now(),
                updated_at=func.now(),

                # No active lease after completion.
                lease_expires_at=None,
            )
            .returning(TaskExecution)
        )

        async with self.db_client() as session:
            async with session.begin():
                result = await session.execute(statement)
                execution = result.scalar_one_or_none()

            return execution

    async def mark_failed(
        self,
        execution_id: int,
        error_message: str,
    ) -> TaskExecution | None:
        """
        Marks an owned execution as failed.
        """

        statement = (
            update(TaskExecution)
            .where(
                TaskExecution.execution_id
                == execution_id,
                TaskExecution.status == "RUNNING",
            )
            .values(
                status="FAILED",
                error_message=error_message,
                finished_at=func.now(),
                updated_at=func.now(),

                # No active lease after failure.
                lease_expires_at=None,
            )
            .returning(TaskExecution)
        )

        async with self.db_client() as session:
            async with session.begin():
                result = await session.execute(statement)
                execution = result.scalar_one_or_none()

            return execution


    async def delete_old_executions(
        self,
        *,
        success_retention_days: int = 7,
        failed_retention_days: int = 30,
    ) -> dict:
        """
        Deletes old completed execution records.

        SUCCESS records:
            Deleted after success_retention_days.

        FAILED records:
            Deleted after failed_retention_days.

        RUNNING records:
            Never deleted by this cleanup method.
        """

        now = datetime.now(timezone.utc)

        success_cutoff = now - timedelta(
            days=success_retention_days
        )

        failed_cutoff = now - timedelta(
            days=failed_retention_days
        )

        statement = (
            delete(TaskExecution)
            .where(
                (
                    (TaskExecution.status == "SUCCESS")
                    & (
                        TaskExecution.finished_at
                        < success_cutoff
                    )
                )
                |
                (
                    (TaskExecution.status == "FAILED")
                    & (
                        TaskExecution.finished_at
                        < failed_cutoff
                    )
                )
            )
            .returning(
                TaskExecution.execution_id,
                TaskExecution.status,
            )
        )

        async with self.db_client() as session:
            async with session.begin():
                result = await session.execute(statement)
                deleted_rows = result.all()

        return {
            "deleted_count": len(deleted_rows),
            "deleted_success": sum(
                1
                for _, status in deleted_rows
                if status == "SUCCESS"
            ),
            "deleted_failed": sum(
                1
                for _, status in deleted_rows
                if status == "FAILED"
            ),
        }