"""Create, process, and index the immutable public-demo workspace.

The marker description and fixed asset name make reruns idempotent. Failure of
either Celery stage exits non-zero, preventing FastAPI from starting.
"""
from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path

from celery.result import AsyncResult
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from celery_app import celery_app
from helpers.config import get_settings
from models.db_schemes import Asset, DataChunk, Project
from models.enums import AssetTypeEnum
from tasks.file_processing import process_project_files
from tasks.index_processing import index_project_task
from utils.file_utils import calculate_file_checksum

MARKER = "public-demo-workspace:v1"
ASSET_NAME = "remote_work_policy.txt"


def _needs_pipeline(*, created: bool, chunk_count: int | None) -> bool:
    """An existing asset is not ready until at least one chunk exists."""
    return created or not int(chunk_count or 0)


async def _ensure_workspace() -> tuple[int, int, bool]:
    settings = get_settings()
    engine = create_async_engine(
        f"postgresql+asyncpg://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}@"
        f"{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
    )
    sessions = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with sessions() as session:
            project = (await session.execute(
                select(Project).where(Project.project_description == MARKER)
            )).scalar_one_or_none()
            created = project is None
            if project is None:
                project = Project(project_description=MARKER)
                session.add(project)
                await session.flush()
            asset = (await session.execute(select(Asset).where(
                Asset.asset_project_id == project.project_id,
                Asset.asset_name == ASSET_NAME,
            ))).scalar_one_or_none()
            target = Path("/app/assets/files") / str(project.project_id) / ASSET_NAME
            target.parent.mkdir(parents=True, exist_ok=True)
            if asset is None:
                shutil.copyfile(Path("/app/demo_assets") / ASSET_NAME, target)
                asset = Asset(
                    asset_name=ASSET_NAME,
                    asset_size=target.stat().st_size,
                    asset_project_id=project.project_id,
                    asset_type=AssetTypeEnum.FILE.value,
                    asset_checksum=calculate_file_checksum(target),
                )
                session.add(asset)
                await session.flush()
                created = True
            chunk_count = await session.scalar(
                select(func.count()).select_from(DataChunk).where(
                    DataChunk.chunk_project_id == project.project_id,
                    DataChunk.chunk_asset_id == asset.asset_id,
                )
            )
            await session.commit()
            # Existence is not readiness: a prior failed run may have created
            # the asset but never dispatched/finished processing.
            return project.project_id, asset.asset_id, _needs_pipeline(
                created=created,
                chunk_count=chunk_count,
            )
    finally:
        await engine.dispose()


def _wait(task_id: str, label: str) -> dict:
    result = AsyncResult(task_id, app=celery_app)
    value = result.get(timeout=int(os.getenv("DEMO_PROVISION_TIMEOUT_SECONDS", "900")))
    if not isinstance(value, dict):
        raise RuntimeError(f"{label} did not return a structured result")
    return value


def main() -> None:
    project_id, asset_id, needs_pipeline = asyncio.run(_ensure_workspace())
    # Always re-run is deliberately avoided after the first success: the
    # provisioner verifies idempotency without duplicating vectors or tasks.
    if needs_pipeline:
        processed = _wait(process_project_files.delay(
            project_id=project_id, asset_id=asset_id, chunk_size=600,
            overlap_size=80, do_reset=0, principal_id="demo-provisioner",
            correlation_id="demo-provisioner", request_metadata={"demo": "true"},
        ).id, "document processing")
        if not processed.get("no_chunks"):
            raise RuntimeError("demo processing completed without chunks")
        indexed = _wait(index_project_task.delay(
            project_id=project_id, do_reset=1, principal_id="demo-provisioner",
            correlation_id="demo-provisioner", request_metadata={"demo": "true"},
        ).id, "document indexing")
        if indexed.get("indexed_chunks", 0) < 1:
            raise RuntimeError("demo index completed without indexed chunks")
    print(f"DEMO_PROJECT_ID={project_id}", flush=True)


if __name__ == "__main__":
    main()
