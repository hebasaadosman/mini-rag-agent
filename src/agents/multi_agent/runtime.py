from typing import Any

from langchain_core.runnables import RunnableConfig

from .graph import MultiAgentGraph
from .state import (
    MultiAgentState,
    TaskStatus,
    build_initial_multi_agent_state,
)


class MultiAgentRuntime:
    """Public execution boundary around the compiled Multi-Agent graph."""

    _THREAD_PREFIX = "multi-agent"

    def __init__(self, graph: MultiAgentGraph) -> None:
        if not isinstance(graph, MultiAgentGraph):
            raise TypeError("graph must be a MultiAgentGraph.")
        self._workflow = graph.compiled_graph
        self._has_checkpointer = graph.has_checkpointer

    async def chat(
        self,
        *,
        thread_id: str,
        message: str,
        project_id: int | None = None,
    ) -> dict[str, Any]:
        initial_state = build_initial_multi_agent_state(
            message,
            project_id=project_id,
            thread_id=self._normalize_thread_id(thread_id),
        )
        config = self._build_config(initial_state["thread_id"])

        graph_input: MultiAgentState = initial_state
        if self._has_checkpointer:
            snapshot = await self._workflow.aget_state(config)
            checkpoint = dict(snapshot.values or {})
            if checkpoint:
                self._validate_project(checkpoint, project_id)
                graph_input = self._new_message_update(
                    checkpoint,
                    initial_state,
                )

        final_state = await self._workflow.ainvoke(
            graph_input,
            config=config,
        )
        return self._public_result(final_state)

    async def resume(
        self,
        *,
        thread_id: str,
        response: str,
        project_id: int | None = None,
    ) -> dict[str, Any]:
        if not self._has_checkpointer:
            raise RuntimeError(
                "A checkpointer is required to resume a Multi-Agent task."
            )

        normalized_thread_id = self._normalize_thread_id(thread_id)
        normalized_response = str(response or "").strip()
        if not normalized_response:
            raise ValueError("response cannot be blank.")

        config = self._build_config(normalized_thread_id)
        snapshot = await self._workflow.aget_state(config)
        checkpoint = dict(snapshot.values or {})
        if checkpoint:
            self._validate_project(checkpoint, project_id)
            graph_input: MultiAgentState = {
                "conversation_event": "resume",
                "gate_decision": None,
                "pending_user_message": normalized_response,
                "error": None,
            }
        else:
            graph_input = build_initial_multi_agent_state(
                normalized_response,
                project_id=project_id,
                thread_id=normalized_thread_id,
            )
            graph_input.update(
                {
                    "conversation_event": "resume",
                    "pending_user_message": normalized_response,
                }
            )

        final_state = await self._workflow.ainvoke(
            graph_input,
            config=config,
        )
        return self._public_result(final_state)

    @classmethod
    def _build_config(cls, thread_id: str) -> RunnableConfig:
        scoped_thread_id = f"{cls._THREAD_PREFIX}:{thread_id}"
        return {
            "configurable": {"thread_id": scoped_thread_id},
            "tags": ["mini-rag", "multi-agent"],
            "metadata": {
                "agent": "multi-agent",
                "thread_id": thread_id,
            },
        }

    @staticmethod
    def _new_message_update(
        checkpoint: dict[str, Any],
        initial_state: MultiAgentState,
    ) -> MultiAgentState:
        update: MultiAgentState = {
            "conversation_event": "new_message",
            "gate_decision": None,
            "user_message": initial_state["user_message"],
            "pending_user_message": None,
            "error": None,
        }
        if "project_id" in initial_state:
            update["project_id"] = initial_state["project_id"]

        try:
            status = TaskStatus(checkpoint.get("task_status"))
        except (TypeError, ValueError):
            return update

        if status in {
            TaskStatus.COMPLETED,
            TaskStatus.CANCELLED,
            TaskStatus.FAILED,
            TaskStatus.IDLE,
        }:
            saved_messages = checkpoint.get("messages")
            update.update(
                {
                    "supervisor_decision": None,
                    "active_agent": None,
                    "resume_target": None,
                    "task_status": TaskStatus.RUNNING.value,
                    "pending_interrupt": None,
                    "handoff_count": 0,
                    "handoff_reason": None,
                    "visited_agents": [],
                    "final_response": None,
                }
            )
            if saved_messages is not None:
                update["messages"] = list(saved_messages)
        return update

    @staticmethod
    def _validate_project(
        checkpoint: dict[str, Any],
        project_id: int | None,
    ) -> None:
        saved_project_id = checkpoint.get("project_id")
        if (
            project_id is not None
            and saved_project_id is not None
            and project_id != saved_project_id
        ):
            raise ValueError(
                "thread_id already belongs to a different project."
            )

    @staticmethod
    def _public_result(state: Any) -> dict[str, Any]:
        if not isinstance(state, dict):
            raise RuntimeError("The Multi-Agent graph returned invalid state.")
        result = state.get("final_response")
        if not isinstance(result, dict):
            raise RuntimeError(
                "The Multi-Agent graph completed without a public response."
            )
        return dict(result)

    @staticmethod
    def _normalize_thread_id(thread_id: str) -> str:
        normalized = str(thread_id or "").strip()
        if not normalized or len(normalized) > 255:
            raise ValueError(
                "thread_id must contain between 1 and 255 characters."
            )
        return normalized
