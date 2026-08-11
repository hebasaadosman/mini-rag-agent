from collections.abc import Callable
from typing import Any
from uuid import uuid4

from .state import AgentName, MultiAgentState, TaskStatus


SupervisorInterruptIdFactory = Callable[[], str]


class SupervisorResumeError(ValueError):
    pass


def build_supervisor_clarification_update(
    *,
    question: str,
    interrupt_id_factory: SupervisorInterruptIdFactory | None = None,
) -> dict[str, Any]:
    normalized_question = str(question or "").strip()
    if not normalized_question:
        raise ValueError("Supervisor clarification question cannot be blank.")

    factory = interrupt_id_factory or _new_interrupt_id
    interrupt_id = str(factory() or "").strip()
    if not interrupt_id or len(interrupt_id) > 255:
        raise ValueError("Supervisor clarification interrupt ID is invalid.")

    clarification = {
        "type": "routing_clarification",
        "question": normalized_question,
        "options": [],
    }
    return {
        "active_agent": AgentName.SUPERVISOR.value,
        "resume_target": AgentName.SUPERVISOR.value,
        "task_status": TaskStatus.WAITING_FOR_USER.value,
        "pending_interrupt": {
            **clarification,
            "interrupt_id": interrupt_id,
        },
        "pending_user_message": None,
        "final_response": {
            "success": True,
            "status": "clarification_required",
            "agent": AgentName.SUPERVISOR.value,
            "answer": None,
            "clarification": clarification,
            "interrupt_id": interrupt_id,
            "error": None,
        },
        "error": None,
    }


def get_supervisor_resume_message(state: MultiAgentState) -> str:
    try:
        task_status = TaskStatus(state.get("task_status"))
        resume_target = AgentName(state.get("resume_target"))
    except (TypeError, ValueError) as exc:
        raise SupervisorResumeError(
            "The supervisor has no pending clarification."
        ) from exc

    pending = state.get("pending_interrupt")
    if (
        task_status is not TaskStatus.WAITING_FOR_USER
        or resume_target is not AgentName.SUPERVISOR
        or not isinstance(pending, dict)
        or pending.get("type") != "routing_clarification"
    ):
        raise SupervisorResumeError(
            "The supervisor has no pending clarification."
        )

    response = str(state.get("pending_user_message") or "").strip()
    if not response:
        raise SupervisorResumeError(
            "The supervisor clarification response is missing."
        )
    return response


def _new_interrupt_id() -> str:
    return uuid4().hex
