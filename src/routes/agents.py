from fastapi import (
    APIRouter,
    Depends,
    Query,
    Request,
    status,
)
from typing import Annotated
from fastapi.responses import StreamingResponse

from agents.knowledge_agent.schemas import (
    KnowledgeAgentRequest,
    KnowledgeAgentResponse,
    KnowledgeAgentResumeRequest,
    KnowledgeAgentMemoryResponse,
)
from agents.knowledge_agent.streaming import encode_sse, with_heartbeat
from agents.multi_agent.api_schemas import (
    MultiAgentChatRequest,
    MultiAgentResponse,
    MultiAgentResumeRequest,
)
from controllers import KnowledgeAgentController
from models.ProjectModel import ProjectModel
from authorization import ProjectAccess, ProjectPermission
from authorization.dependencies import require_project_permission


agents_router = APIRouter(
    prefix="/api/v1/agents",
    tags=["agents"],
)

ProjectReadAccess = Annotated[
    ProjectAccess,
    Depends(require_project_permission(ProjectPermission.READ)),
]
ProjectWriteAccess = Annotated[
    ProjectAccess,
    Depends(require_project_permission(ProjectPermission.WRITE)),
]


@agents_router.post(
    "/{project_id}/chat",
    response_model=MultiAgentResponse,
    status_code=status.HTTP_200_OK,
    summary="Chat with the Multi-Agent supervisor",
)
async def chat_with_multi_agent(
    request: Request,
    project_id: int,
    payload: MultiAgentChatRequest,
    _: ProjectReadAccess,
):
    lock_key = (
        f"multi-agent:{project_id}:{payload.thread_id}"
    )
    async with request.app.agent_thread_locks.acquire(lock_key):
        return await request.app.multi_agent_controller.chat(
            project_id=project_id,
            thread_id=payload.thread_id,
            message=payload.message,
        )


@agents_router.post(
    "/{project_id}/chat/resume",
    response_model=MultiAgentResponse,
    status_code=status.HTTP_200_OK,
    summary="Resume a paused Multi-Agent task",
)
async def resume_multi_agent_chat(
    request: Request,
    project_id: int,
    payload: MultiAgentResumeRequest,
    _: ProjectReadAccess,
):
    lock_key = (
        f"multi-agent:{project_id}:{payload.thread_id}"
    )
    async with request.app.agent_thread_locks.acquire(lock_key):
        return await request.app.multi_agent_controller.resume(
            project_id=project_id,
            thread_id=payload.thread_id,
            response=payload.response,
        )


@agents_router.post(
    "/knowledge/{project_id}/chat",
    response_model=KnowledgeAgentResponse,
    status_code=status.HTTP_200_OK,
)
async def chat_with_knowledge_agent(
    request: Request,
    project_id: int,
    payload: KnowledgeAgentRequest,
    _: ProjectReadAccess,
):
    project_model = (
        await ProjectModel.create_instance(
            db_client=request.app.db_client,
        )
    )

    controller = KnowledgeAgentController(
        generation_client=(
            request.app.generation_client
        ),
        tools_service=(
            request.app
            .knowledge_agent_tools_service
        ),
        project_model=project_model,
        checkpointer=request.app.checkpointer,
        max_memory_messages=request.app.agent_memory_max_messages,
    )

    lock_key = f"{project_id}:{payload.thread_id.strip()}"
    async with request.app.agent_thread_locks.acquire(lock_key):
        return await controller.chat(
            project_id=project_id,
            message=payload.message,
            thread_id=payload.thread_id,
        )


@agents_router.post(
    "/knowledge/{project_id}/chat/stream",
    response_class=StreamingResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {
            "description": "Server-Sent Events from the knowledge agent.",
            "content": {
                "text/event-stream": {
                    "schema": {"type": "string"},
                }
            },
        }
    },
)
async def stream_knowledge_agent_chat(
    request: Request,
    project_id: int,
    payload: KnowledgeAgentRequest,
    _: ProjectReadAccess,
):
    project_model = await ProjectModel.create_instance(
        db_client=request.app.db_client,
    )
    controller = KnowledgeAgentController(
        generation_client=request.app.generation_client,
        tools_service=request.app.knowledge_agent_tools_service,
        project_model=project_model,
        checkpointer=request.app.checkpointer,
        max_memory_messages=request.app.agent_memory_max_messages,
    )
    lock_key = f"{project_id}:{payload.thread_id.strip()}"

    async def event_generator():
        async with request.app.agent_thread_locks.acquire(lock_key):
            events = controller.chat_stream(
                project_id=project_id,
                message=payload.message,
                thread_id=payload.thread_id,
            )
            async for event in with_heartbeat(events):
                if await request.is_disconnected():
                    break
                yield encode_sse(
                    event=str(event["event"]),
                    data=event.get("data") or {},
                )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@agents_router.get(
    "/debug/tools/assets/{project_id}"
)
async def debug_list_project_assets(
    request: Request,
    project_id: int,
    asset_type: str | None = Query(
        default=None,
    ),
    _: ProjectReadAccess = None,
):
    tools_service = (
        request.app
        .knowledge_agent_tools_service
    )

    return await tools_service.list_project_assets(
        project_id=project_id,
        asset_type=asset_type,
    )


@agents_router.get(
    "/debug/tools/search/{project_id}"
)
async def debug_search_project_chunks(
    request: Request,
    project_id: int,
    query: str,
    limit: int = Query(
        default=5,
        ge=1,
        le=20,
    ),
    _: ProjectReadAccess = None,
):
    tools_service = (
        request.app
        .knowledge_agent_tools_service
    )

    return await tools_service.search_project_chunks(
        project_id=project_id,
        query=query,
        limit=limit,
    )


@agents_router.post(
    "/knowledge/{project_id}/chat/resume",
    response_model=KnowledgeAgentResponse,
    status_code=status.HTTP_200_OK,
)
async def resume_knowledge_agent(
    request: Request,
    project_id: int,
    payload: KnowledgeAgentResumeRequest,
    _: ProjectReadAccess,
):
    project_model = await ProjectModel.create_instance(
        db_client=request.app.db_client,
    )
    controller = KnowledgeAgentController(
        generation_client=request.app.generation_client,
        tools_service=request.app.knowledge_agent_tools_service,
        project_model=project_model,
        checkpointer=request.app.checkpointer,
        max_memory_messages=request.app.agent_memory_max_messages,
    )

    lock_key = f"{project_id}:{payload.thread_id.strip()}"
    async with request.app.agent_thread_locks.acquire(lock_key):
        return await controller.resume(
            project_id=project_id,
            thread_id=payload.thread_id,
            response=payload.response,
        )


@agents_router.post(
    "/knowledge/{project_id}/chat/resume/stream",
    response_class=StreamingResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {
            "description": "Resume an interrupted agent as Server-Sent Events.",
            "content": {
                "text/event-stream": {
                    "schema": {"type": "string"},
                }
            },
        }
    },
)
async def stream_resumed_knowledge_agent_chat(
    request: Request,
    project_id: int,
    payload: KnowledgeAgentResumeRequest,
    _: ProjectReadAccess,
):
    project_model = await ProjectModel.create_instance(
        db_client=request.app.db_client,
    )
    controller = KnowledgeAgentController(
        generation_client=request.app.generation_client,
        tools_service=request.app.knowledge_agent_tools_service,
        project_model=project_model,
        checkpointer=request.app.checkpointer,
        max_memory_messages=request.app.agent_memory_max_messages,
    )
    lock_key = f"{project_id}:{payload.thread_id.strip()}"

    async def event_generator():
        async with request.app.agent_thread_locks.acquire(lock_key):
            events = controller.resume_stream(
                project_id=project_id,
                thread_id=payload.thread_id,
                response=payload.response,
            )
            async for event in with_heartbeat(events):
                if await request.is_disconnected():
                    break
                yield encode_sse(
                    event=str(event["event"]),
                    data=event.get("data") or {},
                )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@agents_router.get(
    "/knowledge/{project_id}/memory/{thread_id}",
    response_model=KnowledgeAgentMemoryResponse,
)
async def get_knowledge_agent_memory(
    request: Request,
    project_id: int,
    thread_id: str,
    _: ProjectReadAccess,
):
    project_model = await ProjectModel.create_instance(
        db_client=request.app.db_client,
    )
    controller = KnowledgeAgentController(
        generation_client=request.app.generation_client,
        tools_service=request.app.knowledge_agent_tools_service,
        project_model=project_model,
        checkpointer=request.app.checkpointer,
        max_memory_messages=request.app.agent_memory_max_messages,
    )
    return await controller.get_memory(
        project_id=project_id,
        thread_id=thread_id,
    )


@agents_router.delete(
    "/knowledge/{project_id}/memory/{thread_id}",
    response_model=KnowledgeAgentMemoryResponse,
)
async def clear_knowledge_agent_memory(
    request: Request,
    project_id: int,
    thread_id: str,
    _: ProjectWriteAccess,
    confirm: bool = Query(
        default=False,
        description=(
            "Must be true to permanently clear the thread memory. "
            "Call without confirmation first to preview the operation."
        ),
    ),
):
    project_model = await ProjectModel.create_instance(
        db_client=request.app.db_client,
    )
    controller = KnowledgeAgentController(
        generation_client=request.app.generation_client,
        tools_service=request.app.knowledge_agent_tools_service,
        project_model=project_model,
        checkpointer=request.app.checkpointer,
        max_memory_messages=request.app.agent_memory_max_messages,
    )

    if not confirm:
        memory = await controller.get_memory(
            project_id=project_id,
            thread_id=thread_id,
        )
        if not memory.success:
            return memory

        return memory.model_copy(
            update={
                "success": False,
                "cleared": False,
                "confirmation_required": True,
                "error": (
                    "Memory deletion requires explicit confirmation. "
                    "Repeat the request with confirm=true."
                ),
            }
        )

    lock_key = f"{project_id}:{thread_id.strip()}"
    async with request.app.agent_thread_locks.acquire(lock_key):
        return await controller.clear_memory(
            project_id=project_id,
            thread_id=thread_id,
        )
