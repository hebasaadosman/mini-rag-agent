from enum import Enum
from typing import Any, TypedDict
from typing_extensions import Annotated


def replace_messages(
    current: list[dict[str, Any]] | None,
    update: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Persist the latest bounded canonical conversation snapshot."""

    return list(update or [])



class AgentName(str, Enum):
    SUPERVISOR = "supervisor"
    KNOWLEDGE = "knowledge"
    UTILITY = "utility"
    GENERAL = "general"
    EMAIL = "email"


class TaskStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    WAITING_FOR_USER = "waiting_for_user"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class MultiAgentState(TypedDict, total=False):
    project_id: int
    thread_id: str
    checkpoint_key: str
    conversation_event: str
    gate_decision: dict[str, Any] | None

    user_message: str
    messages: Annotated[list[dict[str, Any]], replace_messages]
    tool_history: list[dict[str, Any]]

    supervisor_decision: dict[str, Any] | None
    active_agent: str | None
    resume_target: str | None

    task_status: str
    pending_interrupt: dict[str, Any] | None
    pending_user_message: str | None
    switch_confirmation_pending: bool
    pending_switch_message: str | None

    handoff_count: int
    handoff_reason: str | None
    visited_agents: list[str]

    final_response: dict[str, Any] | None
    error: str | None


def build_initial_multi_agent_state(
    user_message: str,
    *,
    project_id: int | None = None,
    thread_id: str | None = None,
    checkpoint_key: str | None = None,
) -> MultiAgentState:
    normalized_message = user_message.strip()
    if not normalized_message:
        raise ValueError("user_message cannot be blank.")

    if project_id is not None and (
        not isinstance(project_id, int)
        or isinstance(project_id, bool)
        or project_id < 1
    ):
        raise ValueError("project_id must be a positive integer.")

    normalized_thread_id = None
    if thread_id is not None:
        normalized_thread_id = str(thread_id).strip()
        if not normalized_thread_id or len(normalized_thread_id) > 255:
            raise ValueError(
                "thread_id must contain between 1 and 255 characters."
            )

    normalized_checkpoint_key = None
    if checkpoint_key is not None:
        normalized_checkpoint_key = str(checkpoint_key).strip()
        if not normalized_checkpoint_key or len(normalized_checkpoint_key) > 255:
            raise ValueError("checkpoint_key must contain between 1 and 255 characters.")

    state: MultiAgentState = {
        "conversation_event": "new_message",
        "gate_decision": None,
        "user_message": normalized_message,
        "messages": [],
        "tool_history": [],
        "supervisor_decision": None,
        "active_agent": None,
        "resume_target": None,
        "task_status": TaskStatus.RUNNING.value,
        "pending_interrupt": None,
        "pending_user_message": None,
        "switch_confirmation_pending": False,
        "pending_switch_message": None,
        "handoff_count": 0,
        "handoff_reason": None,
        "visited_agents": [],
        "final_response": None,
        "error": None,
    }

    if project_id is not None:
        state["project_id"] = project_id
    if normalized_thread_id is not None:
        state["thread_id"] = normalized_thread_id
    if normalized_checkpoint_key is not None:
        state["checkpoint_key"] = normalized_checkpoint_key

    return state
