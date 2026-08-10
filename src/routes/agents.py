from fastapi import (
    APIRouter,
    Query,
    Request,
    status,
)

from agents.knowledge_agent.schemas import (
    KnowledgeAgentRequest,
    KnowledgeAgentResponse,
    KnowledgeAgentResumeRequest,
    KnowledgeAgentMemoryResponse,
)
from controllers import KnowledgeAgentController
from models.ProjectModel import ProjectModel


agents_router = APIRouter(
    prefix="/api/v1/agents",
    tags=["agents"],
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


@agents_router.get(
    "/debug/tools/assets/{project_id}"
)
async def debug_list_project_assets(
    request: Request,
    project_id: int,
    asset_type: str | None = Query(
        default=None,
    ),
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


@agents_router.get(
    "/knowledge/{project_id}/memory/{thread_id}",
    response_model=KnowledgeAgentMemoryResponse,
)
async def get_knowledge_agent_memory(
    request: Request,
    project_id: int,
    thread_id: str,
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
