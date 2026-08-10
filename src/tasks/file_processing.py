import asyncio
import logging

from celery_app import celery_app, get_setup_utils
from models.ProjectModel import ProjectModel
from models.db_schemes import DataChunk
from models.enums.AssetTypeEnum import AssetTypeEnum
from models.TaskExecutionModel import TaskExecutionModel
from utils.file_utils import build_asset_file_path, calculate_file_checksum

logger = logging.getLogger(__name__)
from controllers import NLPController, ProcessController
from utils.idempotency import generate_idempotency_key
from models import ResponseSignals
from models.AssetModel import AssetModel
from models.ChunkModel import ChunkModel
from models.ProjectModel import ProjectModel
from models.db_schemes import DataChunk
from models.enums.AssetTypeEnum import AssetTypeEnum
from models.TaskExecutionModel import TaskExecutionModel
logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="tasks.file_processing.process_project_files",
    autoretry_for=(ConnectionError, TimeoutError),
    retry_kwargs={"max_retries": 3, "countdown": 60},
)
def process_project_files(
    self,
    project_id: int,
    asset_id: int | None,
    chunk_size: int,
    overlap_size: int,
    do_reset: int,
):
    return asyncio.run(
        _process_project_files(
            task_instance=self,
            project_id=project_id,
            asset_id=asset_id,
            chunk_size=chunk_size,
            overlap_size=overlap_size,
            do_reset=do_reset,
        )
    )



async def _process_project_files(
    task_instance,
    project_id: int,
    asset_id: int | None,
    chunk_size: int,
    overlap_size: int,
    do_reset: int,
):
    db_engine = None
    vectordb_client = None
    execution_model = None
    execution = None

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

        asset_model = await AssetModel.create_instance(
            db_client=db_client
        )

        chunk_model = await ChunkModel.create_instance(
            db_client=db_client
        )

        execution_model = await TaskExecutionModel.create_instance(
            db_client=db_client
        )

        project = await project_model.get_project_or_create_one(
            project_id=project_id
        )

        if project is None:
            raise ValueError(
                f"Project '{project_id}' was not found."
            )

        process_controller = ProcessController(
            project_id=project.project_id
        )

        # ---------------------------------------------------------
        # 1. Load the assets that should be processed
        # ---------------------------------------------------------

        if asset_id is not None:
            asset_record = await asset_model.get_asset_by_id(
                asset_project_id=project.project_id,
                asset_id=asset_id,
            )

            if asset_record is None:
                raise ValueError(
                    f"No asset found for asset_id '{asset_id}' "
                    f"inside project '{project.project_id}'."
                )

            if asset_record.asset_type != AssetTypeEnum.FILE.value:
                raise ValueError(
                    f"Asset '{asset_id}' is not a file asset."
                )

            assets_to_process = [asset_record]
            operation = "PROCESS_ASSET"

        else:
            assets_to_process = (
                await asset_model.get_all_projects_assets(
                    asset_project_id=project.project_id,
                    asset_type=AssetTypeEnum.FILE.value,
                )
            )

            operation = "PROCESS_PROJECT"

        if not assets_to_process:
            raise ValueError(
                f"No files found for project "
                f"'{project.project_id}'."
            )

        # ---------------------------------------------------------
        # 2. Ensure every asset has a checksum
        # ---------------------------------------------------------

        asset_versions: list[dict] = []

        for current_asset in assets_to_process:
            file_checksum = current_asset.asset_checksum

            if not file_checksum:
                file_path = build_asset_file_path(
                    current_asset
                )

                file_checksum = calculate_file_checksum(
                    file_path
                )

                updated_asset = await asset_model.update_checksum(
                    asset_id=current_asset.asset_id,
                    checksum=file_checksum,
                )

                if updated_asset is None:
                    raise RuntimeError(
                        "Could not save checksum for asset "
                        f"'{current_asset.asset_id}'."
                    )

                current_asset.asset_checksum = file_checksum

            asset_versions.append(
                {
                    "asset_id": current_asset.asset_id,
                    "file_checksum": file_checksum,
                }
            )

        # مهم علشان project key يفضل ثابت بغض النظر عن ترتيب DB
        asset_versions.sort(
            key=lambda item: item["asset_id"]
        )

        # ---------------------------------------------------------
        # 3. Generate the business idempotency key
        # ---------------------------------------------------------

        idempotency_key = generate_idempotency_key(
            operation=operation,
            project_id=project.project_id,
            assets=asset_versions,
            chunk_size=chunk_size,
            overlap_size=overlap_size,
        )

        from uuid import UUID

        celery_task_id = UUID(
            str(task_instance.request.id)
        )

        # ---------------------------------------------------------
        # 4. Atomically claim the execution
        # ---------------------------------------------------------

        execution = (
            await execution_model.try_start_execution(
                idempotency_key=idempotency_key,
                celery_task_id=celery_task_id,
                operation=operation,
                project_id=project.project_id,
                asset_id=(
                    asset_id
                    if asset_id is not None
                    else None
                ),
            )
        )

        # Another execution already owns the same key
        if execution is None:
            existing_execution = (
                await execution_model
                .get_by_idempotency_key(
                    idempotency_key
                )
            )

            if existing_execution is None:
                raise RuntimeError(
                    "An idempotency conflict occurred, "
                    "but the existing execution could not "
                    "be loaded."
                )

            if existing_execution.status == "SUCCESS":
                logger.info(
                    "Returning cached result for "
                    "idempotency_key=%s",
                    idempotency_key,
                )

                previous_result = (
                    existing_execution.result or {}
                )

                return {
                    **previous_result,
                    "idempotent_replay": True,
                    "execution_id": (
                        existing_execution.execution_id
                    ),
                }

            if existing_execution.status == "RUNNING":
                logger.info(
                    "Equivalent task is already running. "
                    "execution_id=%s",
                    existing_execution.execution_id,
                )

                return {
                    "signal": "PROCESS_ALREADY_RUNNING",
                    "execution_id": (
                        existing_execution.execution_id
                    ),
                    "project_id": project.project_id,
                    "asset_id": asset_id,
                    "idempotent_replay": True,
                }

            if existing_execution.status == "FAILED":
                raise RuntimeError(
                    "An identical execution previously failed. "
                    "Failed-execution retry support must reclaim "
                    "the existing record before running again."
                )

            raise RuntimeError(
                "Equivalent execution has unsupported status "
                f"'{existing_execution.status}'."
            )

        # ---------------------------------------------------------
        # 5. Process and atomically replace each asset's chunks
        # ---------------------------------------------------------

        inserted_chunks = 0
        processed_files = 0
        total_files = len(assets_to_process)

        for current_asset in assets_to_process:
            logger.info(
                "Processing asset_id=%s, asset_name=%r, "
                "project_id=%s",
                current_asset.asset_id,
                current_asset.asset_name,
                project.project_id,
            )

            chunks = (
                await process_controller
                .process_file_content(
                    file_id=current_asset.asset_name,
                    chunk_size=chunk_size,
                    overlap_size=overlap_size,
                    do_reset=0,
                )
            )

            if not chunks:
                logger.warning(
                    "No chunks generated for asset_id=%s, "
                    "asset_name=%r",
                    current_asset.asset_id,
                    current_asset.asset_name,
                )
                continue

            chunk_records = [
                DataChunk(
                    chunk_text=chunk.page_content,
                    chunk_metadata=chunk.metadata,
                    chunk_order=index,
                    chunk_project_id=project.project_id,
                    chunk_asset_id=current_asset.asset_id,
                )
                for index, chunk in enumerate(
                    chunks,
                    start=1,
                )
            ]

            # مهم جدًا:
            # delete old asset chunks + insert new chunks
            # داخل transaction واحدة.
            replaced_count = (
                await chunk_model.replace_asset_chunks(
                    project_id=project.project_id,
                    asset_id=current_asset.asset_id,
                    chunk_records=chunk_records,
                )
            )

            inserted_chunks += replaced_count
            processed_files += 1

            progress_percent = round(
                processed_files / total_files * 100,
                2,
            )

            task_instance.update_state(
                state="PROGRESS",
                meta={
                    "stage": "PROCESSING_FILES",
                    "project_id": project.project_id,
                    "asset_id": current_asset.asset_id,
                    "processed_files": processed_files,
                    "total_files": total_files,
                    "inserted_chunks": inserted_chunks,
                    "progress_percent": progress_percent,
                },
            )

        if processed_files == 0:
            raise RuntimeError(
                "No files were processed successfully."
            )

        # ---------------------------------------------------------
        # 6. Store the successful result
        # ---------------------------------------------------------

        final_result = {
            "signal": (
                ResponseSignals.FILE_PROCESS_SUCCESS.value
            ),
            "project_id": project.project_id,
            "asset_id": asset_id,
            "no_chunks": inserted_chunks,
            "no_files": processed_files,
            "execution_id": execution.execution_id,
            "idempotent_replay": False,
        }

        await execution_model.mark_success(
            execution_id=execution.execution_id,
            result_data=final_result,
        )

        logger.info(
            "Successfully inserted %s chunks from %s files. "
            "execution_id=%s",
            inserted_chunks,
            processed_files,
            execution.execution_id,
        )

        return final_result

    except Exception as exc:
        logger.exception(
            "Processing task failed for project_id=%s, "
            "asset_id=%s",
            project_id,
            asset_id,
        )

        # نسجل FAILED فقط لو الـ worker ده هو اللي عمل claim
        if (
            execution is not None
            and execution_model is not None
        ):
            try:
                await execution_model.mark_failed(
                    execution_id=execution.execution_id,
                    error_message=str(exc),
                )

            except Exception:
                logger.exception(
                    "Could not mark execution_id=%s "
                    "as FAILED.",
                    execution.execution_id,
                )

        raise

    finally:
        if vectordb_client is not None:
            try:
                await vectordb_client.disconnect()
            except Exception:
                logger.exception(
                    "Failed to disconnect vector DB client."
                )

        if db_engine is not None:
            try:
                await db_engine.dispose()
            except Exception:
                logger.exception(
                    "Failed to dispose database engine."
                )