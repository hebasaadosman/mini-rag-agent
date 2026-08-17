from celery.result import AsyncResult
from celery_app import celery_app

from typing import Annotated

from fastapi import APIRouter, Depends, Request,FastAPI,status
from fastapi.responses import JSONResponse
from models.ProjectModel import ProjectModel
from controllers import NLPController
import logging
from .schemes.nlp import PushRequest, SearchRequest
from models import ResponseSignals
from models.ChunkModel import ChunkModel
import asyncio
from cohere.errors.too_many_requests_error import TooManyRequestsError
import random
from typing import Any
from tasks.index_processing import index_project_task
from authorization import ProjectAccess, ProjectPermission
from authorization.dependencies import require_project_permission

logger = logging.getLogger("uvicorn.error")
nlp_router = APIRouter(
    prefix="/api/v1/nlp",
    tags=["nlp"],
)

INDEX_PAGE_SIZE = 10
INDEX_MAX_RETRIES = 5
INDEX_BATCH_TIMEOUT_SECONDS = 90
INDEX_MAX_BACKOFF_SECONDS = 60
INDEX_DELAY_BETWEEN_BATCHES_SECONDS = 2

ProjectReadAccess = Annotated[
    ProjectAccess,
    Depends(require_project_permission(ProjectPermission.READ)),
]
ProjectWriteAccess = Annotated[
    ProjectAccess,
    Depends(require_project_permission(ProjectPermission.WRITE)),
]

def is_rate_limit_error(error: Any) -> bool:
   
    error_text = str(error).lower()

    rate_limit_markers = (
        "429",
        "rate limit",
        "too many requests",
        "token rate limit exceeded",
    )

    return any(marker in error_text for marker in rate_limit_markers)
def calculate_retry_delay(attempt: int) -> float:
    
    base_delay = min(
        INDEX_MAX_BACKOFF_SECONDS,
        10 * (2 ** (attempt - 1)),
    )

    jitter = random.uniform(0, 3)

    return base_delay + jitter

@nlp_router.post("/index/push/{project_id}")
async def index_project(
    project_id: int,
    push_request: PushRequest,
    _: ProjectWriteAccess,
):
    task = index_project_task.apply_async(
        kwargs={
            "project_id": project_id,
            "do_reset": push_request.do_reset,
        },
        queue="index_processing",
    )

    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={
            "signal": "INDEXING_TASK_QUEUED",
            "task_id": task.id,
            "project_id": project_id,
        },
    )

@nlp_router.get("/index/info/{project_id}")
async def get_project_index_info(request: Request, project_id: int, access: ProjectReadAccess):
    project_model= await ProjectModel.create_instance(
           db_client=request.app.db_client
   )
    project = (
        await project_model.get_project_by_id(project_id)
        if access.enforced
        else await project_model.get_project_or_create_one(project_id)
    )
    if not project:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"signal": ResponseSignals.PROJECT_NOT_FOUND.value.format(project_id=project_id)},
        )
    nlp_controller = NLPController(
       vectordb_client=request.app.vectordb_client,
         generation_client=request.app.generation_client,
            embedding_client=request.app.embedding_client,
            template_parser=request.app.template_parser
   )
    success, collection_info = await nlp_controller.get_vectordb_collection_info(project)
    if not success:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"signal": ResponseSignals.GET_VECTORDB_COLLECTION_INFO_FAILED.value, "message": collection_info},
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"signal": ResponseSignals.GET_VECTORDB_COLLECTION_INFO_SUCCESS.value, "collection_info": collection_info},
    )
@nlp_router.post("/index/search/{project_id}")
async def search_project_index(request: Request, project_id: int, search_request: SearchRequest, access: ProjectReadAccess):
    project_model= await ProjectModel.create_instance(
           db_client=request.app.db_client
   )
    project = (
        await project_model.get_project_by_id(project_id)
        if access.enforced
        else await project_model.get_project_or_create_one(project_id)
    )
    if not project:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"signal": ResponseSignals.PROJECT_NOT_FOUND.value.format(project_id=project_id)},
        )
    nlp_controller = NLPController(
       vectordb_client=request.app.vectordb_client,
         generation_client=request.app.generation_client,
            embedding_client=request.app.embedding_client,
            template_parser=request.app.template_parser
   )
    success, search_results = await nlp_controller.search_in_vectordb(
        project=project,
        query=search_request.query,
        limit=search_request.limit
    )
    if not success:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"signal": ResponseSignals.SEARCH_VECTORDB_FAILED.value, "message": search_results},
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"signal": ResponseSignals.SEARCH_VECTORDB_SUCCESS.value, "results": search_results},
    )

@nlp_router.post("/index/answer/{project_id}")
async def answer_rag_question(request: Request, project_id: int, search_request: SearchRequest, access: ProjectReadAccess):
    project_model= await ProjectModel.create_instance(
           db_client=request.app.db_client
   )
    project = (
        await project_model.get_project_by_id(project_id)
        if access.enforced
        else await project_model.get_project_or_create_one(project_id)
    )
    if not project:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"signal": ResponseSignals.PROJECT_NOT_FOUND.value.format(project_id=project_id)},
        )
    nlp_controller = NLPController(
       vectordb_client=request.app.vectordb_client,
         generation_client=request.app.generation_client,
            embedding_client=request.app.embedding_client,
            template_parser=request.app.template_parser
   )
    success, answer,full_prompt, chat_history = await nlp_controller.answer_rag_question(
        project=project,
        query=search_request.query,
        limit=search_request.limit
    )
    if not success:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"signal": ResponseSignals.ANSWER_RAG_FAILED.value, "message": answer},
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"signal": ResponseSignals.ANSWER_RAG_SUCCESS.value, "answer": answer,"full_prompt":full_prompt,"chat_history":chat_history},
    )



@nlp_router.get("/index/{project_id}/status/{task_id}")
async def get_index_task_status(
    project_id: int,
    task_id: str,
    _: ProjectReadAccess,
):
    result = AsyncResult(
        task_id,
        app=celery_app,
    )

    response = {
        "task_id": task_id,
        "state": result.state,
    }

    if result.state == "PROGRESS":
        response["progress"] = result.info

    elif result.state == "SUCCESS":
        response["result"] = result.result

    elif result.state == "FAILURE":
        response["error"] = str(result.info)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response,
    )
