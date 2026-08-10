from __future__ import annotations

import asyncio
import logging
import random
from typing import Any

from celery_app import celery_app, get_setup_utils
from controllers import NLPController
from models import ResponseSignals
from models.ChunkModel import ChunkModel
from models.ProjectModel import ProjectModel

logger = logging.getLogger(__name__)


INDEX_PAGE_SIZE = 10
INDEX_MAX_RETRIES = 5
INDEX_BATCH_TIMEOUT_SECONDS = 90
INDEX_MAX_BACKOFF_SECONDS = 60
INDEX_DELAY_BETWEEN_BATCHES_SECONDS = 2


def is_rate_limit_error(error: Any) -> bool:
    error_text = str(error).lower()

    markers = (
        "429",
        "rate limit",
        "too many requests",
        "token rate limit exceeded",
    )

    return any(marker in error_text for marker in markers)


def calculate_retry_delay(attempt: int) -> float:
    base_delay = min(
        INDEX_MAX_BACKOFF_SECONDS,
        10 * (2 ** (attempt - 1)),
    )

    return base_delay + random.uniform(0, 3)


@celery_app.task(
    bind=True,
    name="tasks.index_processing.index_project",
    autoretry_for=(
        ConnectionError,
        TimeoutError,
    ),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def index_project_task(
    self,
    project_id: int,
    do_reset: int = 0,
) -> dict:
    return asyncio.run(
        _index_project(
            task_instance=self,
            project_id=project_id,
            do_reset=do_reset,
        )
    )


async def _index_project(
    task_instance,
    project_id: int,
    do_reset: int,
) -> dict:
    db_engine = None
    vectordb_client = None

    try:
        (
            db_engine,
            db_client,
            _,
            _,
            generation_client,
            embedding_client,
            vectordb_client,
            template_parser,
        ) = await get_setup_utils()

        project_model = await ProjectModel.create_instance(
            db_client=db_client
        )

        chunk_model = await ChunkModel.create_instance(
            db_client=db_client
        )

        project = await project_model.get_project_by_id(
            project_id=project_id
        )

        if project is None:
            raise ValueError(
                f"Project not found: project_id={project_id}"
            )

        nlp_controller = NLPController(
            vectordb_client=vectordb_client,
            generation_client=generation_client,
            embedding_client=embedding_client,
            template_parser=template_parser,
        )

        collection_name = (
            await nlp_controller.create_collection_name(
                project.project_id
            )
        )

        total_chunks = (
            await chunk_model.get_total_chunks_count_by_project_id(
                project.project_id
            )
        )

        if total_chunks == 0:
            raise ValueError(
                f"No chunks found for project_id={project.project_id}"
            )

        # الـ reset يحصل مرة واحدة فقط قبل بداية الـ batches.
        if do_reset == 1:
            collection_exists = await vectordb_client.is_collection_exists(
                collection_name=collection_name
            )

            if collection_exists:
                await vectordb_client.delete_collection(
                    collection_name=collection_name
                )

        # لازم create_collection تكون idempotent:
        # تنشئ الـ collection لو مش موجودة،
        # وما تفشلش لو موجودة بالفعل.
        await vectordb_client.create_collection(
            collection_name=collection_name,
            vector_size=vectordb_client.default_vector_size,
        )

        page_number = 1
        indexed_chunks = 0

        while True:
            page_chunks, _, _ = (
                await chunk_model.get_chunks_by_project_id(
                    project.project_id,
                    page_number=page_number,
                    page_size=INDEX_PAGE_SIZE,
                )
            )

            if not page_chunks:
                break

            batch_indexed = await _index_batch_with_retry(
                nlp_controller=nlp_controller,
                project=project,
                page_chunks=page_chunks,
                project_id=project.project_id,
                page_number=page_number,
            )

            if not batch_indexed:
                raise RuntimeError(
                    "Failed to index batch "
                    f"page={page_number}, project_id={project.project_id}"
                )

            indexed_chunks += len(page_chunks)
            page_number += 1

            progress_percent = round(
                indexed_chunks / total_chunks * 100,
                2,
            )

            task_instance.update_state(
                state="PROGRESS",
                meta={
                    "project_id": project.project_id,
                    "indexed_chunks": indexed_chunks,
                    "total_chunks": total_chunks,
                    "progress_percent": progress_percent,
                    "next_page": page_number,
                },
            )

            logger.info(
                "Indexed project batch. "
                "project_id=%s indexed=%s/%s progress=%.2f%%",
                project.project_id,
                indexed_chunks,
                total_chunks,
                progress_percent,
            )

            await asyncio.sleep(
                INDEX_DELAY_BETWEEN_BATCHES_SECONDS
            )

        return {
            "signal": (
                ResponseSignals
                .INSERT_INTO_VECTORDB_SUCCESS
                .value
            ),
            "project_id": project.project_id,
            "indexed_chunks": indexed_chunks,
            "total_chunks": total_chunks,
            "collection_name": collection_name,
        }

    except Exception:
        logger.exception(
            "Indexing task failed. project_id=%s",
            project_id,
        )
        raise

    finally:
        if vectordb_client is not None:
            try:
                await vectordb_client.disconnect()
            except Exception:
                logger.exception(
                    "Failed to disconnect vector database client."
                )

        if db_engine is not None:
            try:
                await db_engine.dispose()
            except Exception:
                logger.exception(
                    "Failed to dispose database engine."
                )


async def _index_batch_with_retry(
    *,
    nlp_controller: NLPController,
    project,
    page_chunks: list,
    project_id: int,
    page_number: int,
) -> bool:
    last_error: Exception | RuntimeError | None = None

    for attempt in range(1, INDEX_MAX_RETRIES + 1):
        try:
            success, message = await asyncio.wait_for(
                nlp_controller.index_into_vectordb(
                    project,
                    page_chunks,
                ),
                timeout=INDEX_BATCH_TIMEOUT_SECONDS,
            )

            if success:
                return True

            last_error = RuntimeError(str(message))

            if not is_rate_limit_error(message):
                raise last_error

        except asyncio.TimeoutError as exc:
            last_error = TimeoutError(
                "Indexing batch timed out after "
                f"{INDEX_BATCH_TIMEOUT_SECONDS} seconds"
            )

            logger.warning(
                "Indexing batch timeout. "
                "project_id=%s page=%s attempt=%s/%s",
                project_id,
                page_number,
                attempt,
                INDEX_MAX_RETRIES,
            )

        except Exception as exc:
            last_error = exc

            if not is_rate_limit_error(exc):
                raise

        if attempt < INDEX_MAX_RETRIES:
            delay = calculate_retry_delay(attempt)

            logger.warning(
                "Retrying indexing batch. "
                "project_id=%s page=%s attempt=%s/%s "
                "retry_after=%.1fs error=%s",
                project_id,
                page_number,
                attempt,
                INDEX_MAX_RETRIES,
                delay,
                last_error,
            )

            await asyncio.sleep(delay)

    if last_error is not None:
        raise last_error

    return False