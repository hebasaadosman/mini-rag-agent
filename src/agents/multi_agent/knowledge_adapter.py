from collections.abc import Callable
from typing import Any, Protocol

from agents.knowledge_agent.prompts import KNOWLEDGE_AGENT_SYSTEM_PROMPT

from .state import AgentName, MultiAgentState, TaskStatus


class KnowledgeAgentCore(Protocol):
    async def run(
        self,
        *,
        thread_id: str,
        project_id: int,
        user_message: str,
        system_prompt: str,
    ) -> dict[str, Any]: ...

    async def resume(
        self,
        *,
        thread_id: str,
        response: str,
    ) -> dict[str, Any]: ...


KnowledgeAgentFactory = Callable[[int], KnowledgeAgentCore]


class KnowledgeSpecialistAdapter:
    """Map the existing Knowledge Agent contract to MultiAgentState."""

    def __init__(
        self,
        *,
        agent_factory: KnowledgeAgentFactory,
        system_prompt: str = KNOWLEDGE_AGENT_SYSTEM_PROMPT,
        max_memory_messages: int = 40,
    ) -> None:
        if not callable(agent_factory):
            raise TypeError("agent_factory must be callable.")
        if not str(system_prompt or "").strip():
            raise ValueError("system_prompt cannot be blank.")
        if max_memory_messages < 2:
            raise ValueError("max_memory_messages must be at least 2.")

        self._agent_factory = agent_factory
        self._system_prompt = system_prompt.strip()
        self._max_memory_messages = max_memory_messages

    async def __call__(
        self,
        state: MultiAgentState,
    ) -> dict[str, Any]:
        return await self.run(state)

    async def run(
        self,
        state: MultiAgentState,
    ) -> dict[str, Any]:
        context = self._request_context(state)
        if isinstance(context, dict):
            return context

        project_id, thread_id = context
        user_message = str(state.get("user_message") or "").strip()
        if not user_message:
            return self._failure("user_message cannot be blank.")

        try:
            agent = self._agent_factory(project_id)
            result = await agent.run(
                thread_id=thread_id,
                project_id=project_id,
                user_message=user_message,
                system_prompt=self._system_prompt,
            )
        except ValueError as exc:
            return self._failure(str(exc) or "Knowledge request failed.")
        except Exception:
            return self._failure("Failed to run the Knowledge Agent.")

        return self._map_result(
            state,
            result=result,
            input_message=user_message,
        )

    async def resume(
        self,
        state: MultiAgentState,
    ) -> dict[str, Any]:
        context = self._request_context(state)
        if isinstance(context, dict):
            return context

        if not self._is_knowledge_resume(state):
            return self._failure(
                "The Knowledge Agent has no pending clarification."
            )

        response = str(
            state.get("pending_user_message") or ""
        ).strip()
        if not response:
            return self._failure(
                "pending_user_message cannot be blank when resuming."
            )

        project_id, thread_id = context
        try:
            agent = self._agent_factory(project_id)
            result = await agent.resume(
                thread_id=thread_id,
                response=response,
            )
        except ValueError as exc:
            return self._failure(str(exc) or "Knowledge resume failed.")
        except Exception:
            return self._failure("Failed to resume the Knowledge Agent.")

        return self._map_result(
            state,
            result=result,
            input_message=response,
        )

    def _map_result(
        self,
        state: MultiAgentState,
        *,
        result: Any,
        input_message: str,
    ) -> dict[str, Any]:
        if not isinstance(result, dict):
            return self._failure(
                "The Knowledge Agent returned an invalid result."
            )

        status = result.get("status")
        if (
            status == "clarification_required"
            and result.get("success") is True
        ):
            return self._waiting_update(
                state,
                result=result,
                input_message=input_message,
            )
        if status == "completed" and result.get("success") is True:
            return self._completed_update(
                state,
                result=result,
                input_message=input_message,
            )
        if status == "failed" or result.get("success") is False:
            error = str(result.get("error") or "").strip()
            return self._failure(error or "The Knowledge Agent failed.")

        return self._failure(
            "The Knowledge Agent returned an unsupported status."
        )

    def _completed_update(
        self,
        state: MultiAgentState,
        *,
        result: dict[str, Any],
        input_message: str,
    ) -> dict[str, Any]:
        answer = str(result.get("answer") or "").strip()
        if not answer:
            return self._failure(
                "The Knowledge Agent completed without an answer."
            )

        final_response = self._public_response(result)
        final_response.update(
            {
                "success": True,
                "status": "completed",
                "agent": AgentName.KNOWLEDGE.value,
                "answer": answer,
                "clarification": None,
                "interrupt_id": None,
                "error": None,
            }
        )
        return {
            "messages": self._append_conversation_turn(
                state,
                user_content=input_message,
                assistant_content=answer,
            ),
            "active_agent": AgentName.KNOWLEDGE,
            "resume_target": None,
            "task_status": TaskStatus.COMPLETED,
            "pending_interrupt": None,
            "pending_user_message": None,
            "handoff_reason": None,
            "final_response": final_response,
            "error": None,
        }

    def _waiting_update(
        self,
        state: MultiAgentState,
        *,
        result: dict[str, Any],
        input_message: str,
    ) -> dict[str, Any]:
        clarification = result.get("clarification")
        if not isinstance(clarification, dict):
            return self._failure(
                "The Knowledge Agent returned invalid clarification."
            )

        question = str(clarification.get("question") or "").strip()
        raw_options = clarification.get("options") or []
        if (
            not question
            or not isinstance(raw_options, list)
            or any(not isinstance(option, str) for option in raw_options)
        ):
            return self._failure(
                "The Knowledge Agent returned invalid clarification."
            )
        options = [
            option.strip()
            for option in raw_options
            if option.strip()
        ]
        normalized_clarification = {
            "type": "clarification",
            "question": question,
            "options": options,
        }
        interrupt_id = result.get("interrupt_id")
        pending_interrupt = {
            **normalized_clarification,
            "interrupt_id": interrupt_id,
        }

        final_response = self._public_response(result)
        final_response.update(
            {
                "success": True,
                "status": "clarification_required",
                "agent": AgentName.KNOWLEDGE.value,
                "answer": None,
                "clarification": normalized_clarification,
                "interrupt_id": interrupt_id,
                "error": None,
            }
        )
        return {
            "messages": self._append_conversation_turn(
                state,
                user_content=input_message,
                assistant_content=question,
            ),
            "active_agent": AgentName.KNOWLEDGE,
            "resume_target": AgentName.KNOWLEDGE,
            "task_status": TaskStatus.WAITING_FOR_USER,
            "pending_interrupt": pending_interrupt,
            "pending_user_message": None,
            "final_response": final_response,
            "error": None,
        }

    def _append_conversation_turn(
        self,
        state: MultiAgentState,
        *,
        user_content: str,
        assistant_content: str,
    ) -> list[dict[str, str]]:
        history = self._normalize_history(state.get("messages") or [])
        retained_limit = self._max_memory_messages - 2
        retained_history = history[-retained_limit:]
        while retained_history and retained_history[0]["role"] != "user":
            retained_history.pop(0)
        return [
            *retained_history,
            {"role": "user", "content": user_content},
            {"role": "assistant", "content": assistant_content},
        ]

    @staticmethod
    def _normalize_history(messages: Any) -> list[dict[str, str]]:
        if not isinstance(messages, list):
            return []

        normalized: list[dict[str, str]] = []
        for message in messages:
            if not isinstance(message, dict):
                continue
            role = message.get("role")
            content = str(message.get("content") or "").strip()
            if role not in {"user", "assistant"} or not content:
                continue
            normalized.append({"role": role, "content": content})
        return normalized

    @staticmethod
    def _public_response(result: dict[str, Any]) -> dict[str, Any]:
        return {
            "iterations": KnowledgeSpecialistAdapter._safe_int(
                result.get("iterations")
            ),
            "used_chunk_ids": KnowledgeSpecialistAdapter._chunk_ids(
                result.get("used_chunk_ids")
            ),
            "sources": (
                result.get("sources")
                if isinstance(result.get("sources"), list)
                else []
            ),
            "memory_message_count": KnowledgeSpecialistAdapter._safe_int(
                result.get("memory_message_count")
            ),
        }

    @staticmethod
    def _safe_int(value: Any) -> int:
        try:
            normalized = int(value or 0)
        except (TypeError, ValueError):
            return 0
        return max(normalized, 0)

    @staticmethod
    def _chunk_ids(value: Any) -> list[int]:
        if not isinstance(value, list):
            return []
        chunk_ids: list[int] = []
        for raw_chunk_id in value:
            try:
                chunk_id = int(raw_chunk_id)
            except (TypeError, ValueError):
                continue
            if chunk_id > 0 and chunk_id not in chunk_ids:
                chunk_ids.append(chunk_id)
        return chunk_ids

    @staticmethod
    def _request_context(
        state: MultiAgentState,
    ) -> tuple[int, str] | dict[str, Any]:
        project_id = state.get("project_id")
        if (
            not isinstance(project_id, int)
            or isinstance(project_id, bool)
            or project_id < 1
        ):
            return KnowledgeSpecialistAdapter._failure(
                "project_id must be a positive integer."
            )

        thread_id = str(state.get("thread_id") or "").strip()
        if not thread_id or len(thread_id) > 255:
            return KnowledgeSpecialistAdapter._failure(
                "thread_id must contain between 1 and 255 characters."
            )
        return project_id, thread_id

    @staticmethod
    def _is_knowledge_resume(state: MultiAgentState) -> bool:
        try:
            task_status = TaskStatus(state.get("task_status"))
            resume_target = AgentName(state.get("resume_target"))
        except (TypeError, ValueError):
            return False
        return (
            task_status == TaskStatus.WAITING_FOR_USER
            and resume_target == AgentName.KNOWLEDGE
            and isinstance(state.get("pending_interrupt"), dict)
        )

    @staticmethod
    def _failure(message: str) -> dict[str, Any]:
        return {
            "active_agent": AgentName.KNOWLEDGE,
            "task_status": TaskStatus.FAILED,
            "final_response": None,
            "error": message,
        }
