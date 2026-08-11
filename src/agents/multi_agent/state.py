from enum import Enum
from typing import Any, TypedDict


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

    user_message: str
    messages: list[dict[str, Any]]
    tool_history: list[dict[str, Any]]

    supervisor_decision: dict[str, Any] | None
    active_agent: AgentName | None
    resume_target: AgentName | None

    task_status: TaskStatus
    pending_interrupt: dict[str, Any] | None
    pending_user_message: str | None

    handoff_count: int
    handoff_reason: str | None
    visited_agents: list[AgentName]

    final_response: dict[str, Any] | None
    error: str | None


def build_initial_multi_agent_state(
    user_message: str,
    *,
    project_id: int | None = None,
    thread_id: str | None = None,
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

    state: MultiAgentState = {
        "user_message": normalized_message,
        "messages": [],
        "tool_history": [],
        "supervisor_decision": None,
        "active_agent": None,
        "resume_target": None,
        "task_status": TaskStatus.RUNNING,
        "pending_interrupt": None,
        "pending_user_message": None,
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

    return state
