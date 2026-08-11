from typing import Any

from .specialist_schemas import HandoffReason
from .state import AgentName, MultiAgentState, TaskStatus


DEFAULT_MAX_HANDOFFS = 3


def build_handoff_update(
    state: MultiAgentState,
    *,
    from_agent: AgentName,
    reason: HandoffReason,
    max_handoffs: int = DEFAULT_MAX_HANDOFFS,
) -> dict[str, Any]:
    if max_handoffs < 1:
        raise ValueError("max_handoffs must be at least 1.")

    try:
        current_count = int(state.get("handoff_count", 0))
    except (TypeError, ValueError):
        return _handoff_failure(
            from_agent,
            "The checkpoint contains an invalid handoff_count.",
        )

    if current_count < 0:
        return _handoff_failure(
            from_agent,
            "The checkpoint contains an invalid handoff_count.",
        )

    next_count = current_count + 1
    if next_count > max_handoffs:
        return _handoff_failure(
            from_agent,
            "The request exceeded the handoff limit.",
        )

    raw_visited_agents = state.get("visited_agents") or []
    if not isinstance(raw_visited_agents, list):
        return _handoff_failure(
            from_agent,
            "The checkpoint contains invalid visited_agents.",
        )

    visited_agents: list[AgentName] = []
    for raw_agent in raw_visited_agents:
        try:
            agent = AgentName(raw_agent)
        except (TypeError, ValueError):
            return _handoff_failure(
                from_agent,
                "The checkpoint contains invalid visited_agents.",
            )
        if agent not in visited_agents:
            visited_agents.append(agent)

    if from_agent not in visited_agents:
        visited_agents.append(from_agent)

    return {
        "supervisor_decision": None,
        "active_agent": from_agent.value,
        "resume_target": None,
        "task_status": TaskStatus.RUNNING.value,
        "pending_interrupt": None,
        "pending_user_message": None,
        "handoff_count": next_count,
        "handoff_reason": reason.value,
        "visited_agents": [agent.value for agent in visited_agents],
        "final_response": None,
        "error": None,
    }


def _handoff_failure(
    from_agent: AgentName,
    message: str,
) -> dict[str, Any]:
    return {
        "active_agent": from_agent.value,
        "task_status": TaskStatus.FAILED.value,
        "final_response": None,
        "error": message,
    }
