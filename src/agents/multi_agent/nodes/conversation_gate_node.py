from ..conversation_gate import (
    ConversationGate,
    ConversationGateEventError,
    ConversationGateStateError,
)
from ..state import MultiAgentState, TaskStatus


class ConversationGateNode:
    """Adapt the deterministic conversation gate to a LangGraph state update."""

    async def __call__(self, state: MultiAgentState) -> dict:
        try:
            decision = ConversationGate.decide(
                state,
                state.get("conversation_event"),
            )
        except (
            ConversationGateEventError,
            ConversationGateStateError,
        ) as exc:
            return {
                "gate_decision": None,
                "active_agent": None,
                "task_status": TaskStatus.FAILED.value,
                "error": str(exc),
            }

        return {
            "gate_decision": {
                "route": decision.route.value,
                "target": (
                    decision.target.value
                    if decision.target is not None
                    else None
                ),
                "reason": decision.reason,
            },
            "error": None,
        }
