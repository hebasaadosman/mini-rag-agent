from typing import Any

from .graph import KnowledgeAgentGraph


class KnowledgeAgent:
    """
    Public facade used by controllers and tests.

    Controllers do not need to know how the
    internal LangGraph nodes are organized.
    """

    def __init__(
        self,
        *,
        project_id: int,
        llm_provider,
        tool_registry,
        checkpointer=None,
        max_iterations: int = 5,
        max_memory_messages: int = 40,
    ) -> None:
        self._graph_agent = (
            KnowledgeAgentGraph(
                project_id=project_id,
                checkpointer=checkpointer,
                llm_provider=llm_provider,
                tool_registry=tool_registry,
                max_iterations=max_iterations,
                max_memory_messages=max_memory_messages,
            )
        )

    async def run(
        self,
        *,
        thread_id: str,
        project_id: int,
        user_message: str,
        system_prompt: str,
    ) -> dict[str, Any]:
        return await self._graph_agent.run(
            thread_id=thread_id,
            user_message=user_message,
            system_prompt=system_prompt,
        )

    async def resume(
        self,
        *,
        thread_id: str,
        response: str,
    ) -> dict[str, Any]:
        return await self._graph_agent.resume(
            thread_id=thread_id,
            response=response,
        )

    async def get_memory(self, *, thread_id: str) -> dict[str, Any]:
        return await self._graph_agent.get_memory(thread_id=thread_id)

    async def clear_memory(self, *, thread_id: str) -> None:
        await self._graph_agent.clear_memory(thread_id=thread_id)
