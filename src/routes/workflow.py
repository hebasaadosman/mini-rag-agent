from celery import chain
from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from tasks.file_processing import process_project_files
from tasks.index_processing import index_project_task
from .schemes.data import ProcessRequest


workflow_router = APIRouter(
    prefix="/api/v1/workflow",
    tags=["workflow"],
)


@workflow_router.post("/process-and-push/{project_id}")
async def process_and_push(
    project_id: int,
    process_request: ProcessRequest,
):
    workflow = chain(
        process_project_files.si(
            project_id=project_id,
            asset_id=process_request.asset_id,
            chunk_size=process_request.chunk_size,
            overlap_size=process_request.overlap_size,
            do_reset=process_request.do_reset,
        ).set(queue="file_processing"),

        index_project_task.si(
            project_id=project_id,
            do_reset=process_request.do_reset,
        ).set(queue="index_processing"),
    )

    result = workflow.apply_async()

    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={
            "signal": "PROCESS_AND_PUSH_WORKFLOW_QUEUED",
            "workflow_id": result.id,
            "project_id": project_id,
        },
    )
