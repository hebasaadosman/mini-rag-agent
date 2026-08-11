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
) -> MultiAgentState:
    normalized_message = user_message.strip()
    if not normalized_message:
        raise ValueError("user_message cannot be blank.")

    return {
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
