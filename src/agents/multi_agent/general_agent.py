import asyncio
from typing import Any

from .general_prompts import build_general_agent_system_prompt
from .handoff import build_handoff_update
from .specialist_parser import (
    SpecialistResponseParseError,
    SpecialistResponseParser,
)
from .specialist_hitl import (
    ClarificationIdFactory,
    SpecialistResumeError,
    build_specialist_clarification_update,
    get_specialist_resume_message,
)
from .specialist_schemas import SpecialistAction
from .state import AgentName, MultiAgentState, TaskStatus


class GeneralAgent:
    def __init__(
        self,
        *,
        llm_provider,
        max_tokens: int = 500,
        temperature: float = 0.2,
        max_memory_messages: int = 40,
        interrupt_id_factory: ClarificationIdFactory | None = None,
    ) -> None:
        if max_memory_messages < 2:
            raise ValueError("max_memory_messages must be at least 2.")

        self._llm_provider = llm_provider
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._max_memory_messages = max_memory_messages
        self._interrupt_id_factory = interrupt_id_factory

    async def __call__(
        self,
        state: MultiAgentState,
    ) -> dict[str, Any]:
        user_message = str(state.get("user_message") or "").strip()
        if not user_message:
            return self._failure("user_message cannot be blank.")

        return await self._run(state, user_message=user_message)

    async def resume(
        self,
        state: MultiAgentState,
    ) -> dict[str, Any]:
        try:
            response = get_specialist_resume_message(
                state,
                target_agent=AgentName.GENERAL,
            )
        except SpecialistResumeError as exc:
            return self._failure(str(exc))

        return await self._run(state, user_message=response)

    async def _run(
        self,
        state: MultiAgentState,
        *,
        user_message: str,
    ) -> dict[str, Any]:

        canonical_history = self._normalize_history(
            state.get("messages") or []
        )

        try:
            chat_history = self._build_provider_history(
                canonical_history
            )
            content = await asyncio.to_thread(
                self._llm_provider.generate_text,
                user_message,
                chat_history=chat_history,
                max_tokens=self._max_tokens,
                temperature=self._temperature,
            )
        except Exception:
            return self._failure("Failed to call the general agent LLM.")

        try:
            response = SpecialistResponseParser.parse(content)
        except SpecialistResponseParseError:
            response = await self._repair_response(
                user_message=user_message,
                chat_history=chat_history,
            )
            if response is None:
                return self._failure(
                    "The general agent returned an invalid response."
                )

        if response.action == SpecialistAction.HANDOFF:
            return build_handoff_update(
                state,
                from_agent=AgentName.GENERAL,
                reason=response.handoff_reason,
            )

        if response.action == SpecialistAction.CLARIFICATION:
            try:
                return build_specialist_clarification_update(
                    state,
                    from_agent=AgentName.GENERAL,
                    input_message=user_message,
                    question=response.question,
                    options=response.options,
                    max_memory_messages=self._max_memory_messages,
                    interrupt_id_factory=self._interrupt_id_factory,
                )
            except ValueError:
                return self._failure(
                    "The general agent returned invalid clarification."
                )

        normalized_answer = response.answer

        retained_limit = self._max_memory_messages - 2
        retained_history = (
            canonical_history[-retained_limit:]
            if retained_limit
            else []
        )
        while (
            retained_history
            and retained_history[0]["role"] != "user"
        ):
            retained_history.pop(0)

        messages = [
            *retained_history,
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": normalized_answer},
        ]

        return {
            "messages": messages,
            "active_agent": AgentName.GENERAL.value,
            "resume_target": None,
            "task_status": TaskStatus.COMPLETED.value,
            "pending_interrupt": None,
            "pending_user_message": None,
            "handoff_reason": None,
            "final_response": {
                "success": True,
                "status": TaskStatus.COMPLETED.value,
                "agent": AgentName.GENERAL.value,
                "answer": normalized_answer,
            },
            "error": None,
        }

    async def _repair_response(
        self,
        *,
        user_message: str,
        chat_history: list[dict[str, Any]],
    ):
        repair_prompt = (
            "Your previous response did not match the required JSON "
            "contract. Re-evaluate the original user request below and "
            "return exactly one valid JSON object using one of the answer, "
            "clarification, or handoff shapes from the system prompt. Do "
            "not use Markdown or add commentary.\n\nOriginal user request:\n"
            f"{user_message}"
        )
        try:
            repaired_content = await asyncio.to_thread(
                self._llm_provider.generate_text,
                repair_prompt,
                chat_history=chat_history,
                max_tokens=self._max_tokens,
                temperature=0,
            )
            return SpecialistResponseParser.parse(repaired_content)
        except Exception:
            return None

    def _build_provider_history(
        self,
        canonical_history: list[dict[str, str]],
    ) -> list[dict[str, Any]]:
        role_map = {
            "user": self._llm_provider.enums.USER.value,
            "assistant": self._llm_provider.enums.ASSISTANT.value,
        }
        history = [
            self._llm_provider.construct_prompt(
                prompt=build_general_agent_system_prompt(),
                role=self._llm_provider.enums.SYSTEM.value,
            )
        ]

        for message in canonical_history:
            history.append(
                self._llm_provider.construct_prompt(
                    prompt=message["content"],
                    role=role_map[message["role"]],
                )
            )

        return history

    @staticmethod
    def _normalize_history(
        messages: list[dict[str, Any]],
    ) -> list[dict[str, str]]:
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
    def _failure(message: str) -> dict[str, Any]:
        return {
            "active_agent": AgentName.GENERAL.value,
            "resume_target": None,
            "task_status": TaskStatus.FAILED.value,
            "pending_interrupt": None,
            "pending_user_message": None,
            "final_response": None,
            "error": message,
        }
