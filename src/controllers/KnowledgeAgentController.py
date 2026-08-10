from typing import Any

from agents.knowledge_agent.prompts import (
    KNOWLEDGE_AGENT_SYSTEM_PROMPT,
)
from agents.knowledge_agent.schemas import (
    KnowledgeAgentResponse,
    KnowledgeAgentSource,
    KnowledgeAgentClarification,
    KnowledgeAgentMemoryResponse,
)
from agents.knowledge_agent.service import KnowledgeAgent
from agents.tools import (
     ListProjectAssetsTool,
    SearchProjectChunksTool,
    ToolRegistry,
    SearchAssetsByNameTool,
    GetAssetDetailsTool,
    ReadAssetTool,
    RequestClarificationTool,
)
from models.ProjectModel import ProjectModel

from .BaseController import BaseController


class KnowledgeAgentController(BaseController):
    def __init__(
        self,
        *,
        generation_client,
        tools_service,
        project_model: ProjectModel,
        max_iterations: int = 5,
        checkpointer=None,
        max_memory_messages: int = 40,
    ) -> None:
        super().__init__()

        self.generation_client = generation_client
        self.tools_service = tools_service
        self.project_model = project_model
        self.max_iterations = max_iterations
        self.checkpointer = checkpointer
        self.max_memory_messages = max_memory_messages

    async def chat(
        self,
        *,
        project_id: int,
        thread_id: str,
        message: str,
    ) -> KnowledgeAgentResponse:
        normalized_message = message.strip()
        normalized_thread_id = thread_id.strip()

        if not normalized_message:
            return KnowledgeAgentResponse(
                success=False,
                status="failed",
                project_id=project_id,
                answer=None,
                iterations=0,
                sources=[],
                error="The message cannot be empty.",
            )

        if not normalized_thread_id:
            return KnowledgeAgentResponse(
                success=False,
                status="failed",
                project_id=project_id,
                answer=None,
                iterations=0,
                sources=[],
                error="The thread_id cannot be empty.",
            )

        project = await self.project_model.get_project_by_id(
            project_id
        )

        if project is None:
            return KnowledgeAgentResponse(
                success=False,
                status="failed",
                project_id=project_id,
                answer=None,
                iterations=0,
                sources=[],
                error=(
                    f"Project with ID {project_id} "
                    "was not found."
                ),
            )

        agent = self._build_agent(project_id=project_id)

        try:
            result = await agent.run(
                project_id=project_id,
                thread_id=normalized_thread_id,
                user_message=normalized_message,
                system_prompt=KNOWLEDGE_AGENT_SYSTEM_PROMPT,
            )
        except ValueError as exc:
            return KnowledgeAgentResponse(
                success=False,
                status="failed",
                project_id=project_id,
                error=str(exc),
            )

        sources = self._extract_sources(
            tool_history=(
                result.get("tool_history")
                or []
            ),
            used_chunk_ids=(
                result.get("used_chunk_ids")
                or []
            ),
        )

        return KnowledgeAgentResponse(
            success=bool(
                result.get("success")
            ),
            status=result.get("status", "failed"),
            project_id=project_id,
            answer=result.get("answer"),
            iterations=int(
                result.get("iterations") or 0
            ),
            sources=sources,
            clarification=(
                KnowledgeAgentClarification.model_validate(
                    result["clarification"]
                )
                if result.get("clarification")
                else None
            ),
            interrupt_id=result.get("interrupt_id"),
            memory_message_count=int(
                result.get("memory_message_count") or 0
            ),
            error=result.get("error"),
        )

    async def resume(
        self,
        *,
        project_id: int,
        thread_id: str,
        response: str,
    ) -> KnowledgeAgentResponse:
        normalized_thread_id = thread_id.strip()
        normalized_response = response.strip()

        if not normalized_thread_id or not normalized_response:
            return KnowledgeAgentResponse(
                success=False,
                status="failed",
                project_id=project_id,
                error="thread_id and response cannot be empty.",
            )

        project = await self.project_model.get_project_by_id(project_id)
        if project is None:
            return KnowledgeAgentResponse(
                success=False,
                status="failed",
                project_id=project_id,
                error=f"Project with ID {project_id} was not found.",
            )

        agent = self._build_agent(project_id=project_id)
        try:
            result = await agent.resume(
                thread_id=normalized_thread_id,
                response=normalized_response,
            )
        except ValueError as exc:
            return KnowledgeAgentResponse(
                success=False,
                status="failed",
                project_id=project_id,
                error=str(exc),
            )

        sources = self._extract_sources(
            tool_history=result.get("tool_history") or [],
            used_chunk_ids=result.get("used_chunk_ids") or [],
        )

        return KnowledgeAgentResponse(
            success=bool(result.get("success")),
            status=result.get("status", "failed"),
            project_id=project_id,
            answer=result.get("answer"),
            iterations=int(result.get("iterations") or 0),
            sources=sources,
            clarification=(
                KnowledgeAgentClarification.model_validate(
                    result["clarification"]
                )
                if result.get("clarification")
                else None
            ),
            interrupt_id=result.get("interrupt_id"),
            memory_message_count=int(
                result.get("memory_message_count") or 0
            ),
            error=result.get("error"),
        )

    async def get_memory(
        self,
        *,
        project_id: int,
        thread_id: str,
    ) -> KnowledgeAgentMemoryResponse:
        normalized_thread_id = thread_id.strip()
        if not normalized_thread_id:
            return KnowledgeAgentMemoryResponse(
                success=False,
                project_id=project_id,
                thread_id=normalized_thread_id,
                exists=False,
                error="The thread_id cannot be empty.",
            )

        project = await self.project_model.get_project_by_id(project_id)
        if project is None:
            return KnowledgeAgentMemoryResponse(
                success=False,
                project_id=project_id,
                thread_id=normalized_thread_id,
                exists=False,
                error=f"Project with ID {project_id} was not found.",
            )

        agent = self._build_agent(project_id=project_id)
        memory = await agent.get_memory(thread_id=normalized_thread_id)
        return KnowledgeAgentMemoryResponse(
            success=True,
            project_id=project_id,
            thread_id=normalized_thread_id,
            **memory,
        )

    async def clear_memory(
        self,
        *,
        project_id: int,
        thread_id: str,
    ) -> KnowledgeAgentMemoryResponse:
        normalized_thread_id = thread_id.strip()
        if not normalized_thread_id:
            return KnowledgeAgentMemoryResponse(
                success=False,
                project_id=project_id,
                thread_id=normalized_thread_id,
                exists=False,
                error="The thread_id cannot be empty.",
            )

        project = await self.project_model.get_project_by_id(project_id)
        if project is None:
            return KnowledgeAgentMemoryResponse(
                success=False,
                project_id=project_id,
                thread_id=normalized_thread_id,
                exists=False,
                error=f"Project with ID {project_id} was not found.",
            )

        agent = self._build_agent(project_id=project_id)
        before = await agent.get_memory(thread_id=normalized_thread_id)
        await agent.clear_memory(thread_id=normalized_thread_id)
        return KnowledgeAgentMemoryResponse(
            success=True,
            project_id=project_id,
            thread_id=normalized_thread_id,
            exists=False,
            message_count=0,
            pending_clarification=False,
            cleared=before["exists"],
        )

    def _build_agent(self, *, project_id: int) -> KnowledgeAgent:
        return KnowledgeAgent(
            project_id=project_id,
            llm_provider=self.generation_client,
            tool_registry=self._build_tool_registry(project_id=project_id),
            max_iterations=self.max_iterations,
            checkpointer=self.checkpointer,
            max_memory_messages=self.max_memory_messages,
        )

    def _build_tool_registry(
        self,
        *,
        project_id: int,
    ) -> ToolRegistry:
        """
        Build a registry scoped to the current project.

        The LLM can choose a tool, but it cannot change
        the project_id controlled by the backend.
        """

        registry = ToolRegistry()

        registry.register_tool(RequestClarificationTool())

        registry.register_tool(
            SearchProjectChunksTool(
                tools_service=self.tools_service,
                project_id=project_id,
            )
        )
        registry.register_tool(
        ListProjectAssetsTool(
            tools_service=self.tools_service,
            project_id=project_id,
            )
       )
        registry.register_tool(
        SearchAssetsByNameTool(
            tools_service=self.tools_service,
            project_id=project_id,
           )
        )
        registry.register_tool(
        GetAssetDetailsTool(
            tools_service=self.tools_service,
            project_id=project_id,
           )
        )
        registry.register_tool(
            ReadAssetTool(
                tools_service=self.tools_service,
                project_id=project_id,
                asset_id=0,  # Placeholder, actual asset_id should be provided at execution time
            )
        )

        return registry
    @staticmethod
    def _extract_sources(
        *,
        tool_history: list[dict[str, Any]],
        used_chunk_ids: list[int],
    ) -> list[KnowledgeAgentSource]:
        """
        Return only sources explicitly cited by the model.

        Any chunk ID that was not present in a real tool result
        is ignored, even if the model returned it.
        """

        if not used_chunk_ids:
            return []

        source_by_chunk_id: dict[
            int,
            KnowledgeAgentSource,
        ] = {}

        for history_item in tool_history:
            if (
                history_item.get("tool_name")
                != "search_project_chunks"
            ):
                continue

            execution_result = (
                history_item.get(
                    "execution_result"
                )
                or {}
            )

            if not execution_result.get("success"):
                continue

            tool_result = (
                execution_result.get("result")
                or {}
            )

            if not tool_result.get("success"):
                continue

            search_results = (
                tool_result.get("results")
                or []
            )

            for item in search_results:
                chunk_id = item.get("chunk_id")

                if not isinstance(chunk_id, int):
                    continue

                source_by_chunk_id[chunk_id] = (
                    KnowledgeAgentSource(
                        asset_id=item.get(
                            "asset_id"
                        ),
                        asset_name=item.get(
                            "asset_name"
                        ),
                        chunk_id=chunk_id,
                        score=item.get("score"),
                    )
                )

        selected_sources: list[
            KnowledgeAgentSource
        ] = []

        seen_chunk_ids: set[int] = set()

        # Preserve the citation order returned by the model.
        for chunk_id in used_chunk_ids:
            if chunk_id in seen_chunk_ids:
                continue

            source = source_by_chunk_id.get(
                chunk_id
            )

            # Protect against invented or invalid chunk IDs.
            if source is None:
                continue

            seen_chunk_ids.add(chunk_id)
            selected_sources.append(source)

        return selected_sources
