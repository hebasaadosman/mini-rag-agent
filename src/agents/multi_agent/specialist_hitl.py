from collections.abc import Callable
from typing import Any
from uuid import uuid4

from .state import AgentName, MultiAgentState, TaskStatus


ClarificationIdFactory = Callable[[], str]


class SpecialistResumeError(ValueError):
    pass


def build_specialist_clarification_update(
    state: MultiAgentState,
    *,
    from_agent: AgentName,
    input_message: str,
    question: str,
    options: list[str] | None = None,
    max_memory_messages: int = 40,
    interrupt_id_factory: ClarificationIdFactory | None = None,
) -> dict[str, Any]:
    if max_memory_messages < 2:
        raise ValueError("max_memory_messages must be at least 2.")

    normalized_input = str(input_message or "").strip()
    normalized_question = str(question or "").strip()
    if not normalized_input:
        raise ValueError("input_message cannot be blank.")
    if not normalized_question:
        raise ValueError("question cannot be blank.")

    normalized_options = _normalize_options(options or [])
    interrupt_id = _resolve_interrupt_id(
        state,
        from_agent=from_agent,
        question=normalized_question,
        options=normalized_options,
        interrupt_id_factory=interrupt_id_factory or _new_interrupt_id,
    )
    clarification = {
        "type": "clarification",
        "question": normalized_question,
        "options": normalized_options,
    }
    messages = _append_conversation_turn(
        state.get("messages"),
        user_content=normalized_input,
        assistant_content=normalized_question,
        max_memory_messages=max_memory_messages,
    )
    return {
        "messages": messages,
        "active_agent": from_agent,
        "resume_target": from_agent,
        "task_status": TaskStatus.WAITING_FOR_USER,
        "pending_interrupt": {
            **clarification,
            "interrupt_id": interrupt_id,
        },
        "pending_user_message": None,
        "handoff_reason": None,
        "final_response": {
            "success": True,
            "status": "clarification_required",
            "agent": from_agent.value,
            "answer": None,
            "clarification": clarification,
            "interrupt_id": interrupt_id,
            "error": None,
        },
        "error": None,
    }


def get_specialist_resume_message(
    state: MultiAgentState,
    *,
    target_agent: AgentName,
) -> str:
    try:
        task_status = TaskStatus(state.get("task_status"))
        resume_target = AgentName(state.get("resume_target"))
    except (TypeError, ValueError) as exc:
        raise SpecialistResumeError(
            "The specialist has no pending clarification."
        ) from exc

    if (
        task_status != TaskStatus.WAITING_FOR_USER
        or resume_target != target_agent
        or not isinstance(state.get("pending_interrupt"), dict)
    ):
        raise SpecialistResumeError(
            "The specialist has no pending clarification."
        )

    raw_response = state.get("pending_user_message")
    if not isinstance(raw_response, str):
        raise SpecialistResumeError(
            "pending_user_message must be a string when resuming."
        )
    response = raw_response.strip()
    if not response:
        raise SpecialistResumeError(
            "pending_user_message cannot be blank when resuming."
        )
    return response


def _normalize_options(options: list[str]) -> list[str]:
    if not isinstance(options, list):
        raise ValueError("options must be a list.")
    if len(options) > 20:
        raise ValueError("options cannot contain more than 20 values.")

    normalized: list[str] = []
    for option in options:
        if not isinstance(option, str) or not option.strip():
            raise ValueError("clarification options must be non-empty strings.")
        value = option.strip()
        if value not in normalized:
            normalized.append(value)
    return normalized


def _resolve_interrupt_id(
    state: MultiAgentState,
    *,
    from_agent: AgentName,
    question: str,
    options: list[str],
    interrupt_id_factory: ClarificationIdFactory,
) -> str:
    pending = state.get("pending_interrupt")
    try:
        resume_target = AgentName(state.get("resume_target"))
    except (TypeError, ValueError):
        resume_target = None

    if (
        resume_target == from_agent
        and isinstance(pending, dict)
        and str(pending.get("question") or "").strip() == question
        and pending.get("options") == options
    ):
        existing_id = str(pending.get("interrupt_id") or "").strip()
        if existing_id:
            return existing_id

    interrupt_id = str(interrupt_id_factory() or "").strip()
    if not interrupt_id:
        raise ValueError("interrupt_id_factory returned a blank ID.")
    return interrupt_id


def _append_conversation_turn(
    raw_messages: Any,
    *,
    user_content: str,
    assistant_content: str,
    max_memory_messages: int,
) -> list[dict[str, str]]:
    messages = _normalize_history(raw_messages)
    retained_limit = max_memory_messages - 2
    retained = messages[-retained_limit:] if retained_limit else []
    while retained and retained[0]["role"] != "user":
        retained.pop(0)
    return [
        *retained,
        {"role": "user", "content": user_content},
        {"role": "assistant", "content": assistant_content},
    ]


def _normalize_history(raw_messages: Any) -> list[dict[str, str]]:
    if not isinstance(raw_messages, list):
        return []

    normalized: list[dict[str, str]] = []
    for message in raw_messages:
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        content = str(message.get("content") or "").strip()
        if role not in {"user", "assistant"} or not content:
            continue
        normalized.append({"role": role, "content": content})
    return normalized


def _new_interrupt_id() -> str:
    return uuid4().hex
