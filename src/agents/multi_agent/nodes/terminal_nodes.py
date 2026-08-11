from typing import Any

from ..conversation_gate import ConversationRoute
from ..state import AgentName, MultiAgentState, TaskStatus


class FailureNode:
    """Finish an invalid or failed workflow with a safe public response."""

    async def __call__(self, state: MultiAgentState) -> dict[str, Any]:
        return self.build_update(state.get("error"))

    @staticmethod
    def build_update(error: Any) -> dict[str, Any]:
        normalized_error = str(error or "").strip()
        if not normalized_error:
            normalized_error = "The multi-agent workflow failed."

        return {
            "active_agent": None,
            "resume_target": None,
            "task_status": TaskStatus.FAILED.value,
            "pending_interrupt": None,
            "pending_user_message": None,
            "final_response": {
                "success": False,
                "status": TaskStatus.FAILED.value,
                "agent": None,
                "answer": None,
                "error": normalized_error,
            },
            "error": normalized_error,
        }


class GateRejectionNode:
    """Return a deterministic response for a rejected conversation event."""

    async def __call__(self, state: MultiAgentState) -> dict[str, Any]:
        reason = _gate_reason(state, ConversationRoute.REJECT)
        if reason is None:
            return FailureNode.build_update(
                "The conversation rejection decision is invalid."
            )

        return {
            "final_response": {
                "success": False,
                "status": "rejected",
                "agent": None,
                "answer": None,
                "error": reason,
            },
            "error": None,
        }


class GateSwitchConfirmationNode:
    """Ask before abandoning a specialist task that is waiting for input."""

    async def __call__(self, state: MultiAgentState) -> dict[str, Any]:
        reason = _gate_reason(
            state,
            ConversationRoute.REQUEST_SWITCH_CONFIRMATION,
        )
        try:
            task_status = TaskStatus(state.get("task_status"))
            waiting_agent = AgentName(state.get("resume_target"))
        except (TypeError, ValueError):
            task_status = None
            waiting_agent = None

        if (
            task_status is not TaskStatus.WAITING_FOR_USER
            or waiting_agent is None
            or not isinstance(state.get("pending_interrupt"), dict)
        ):
            return FailureNode.build_update(
                "The pending task cannot be identified."
            )
        if reason is None:
            return FailureNode.build_update(
                "The switch-confirmation decision is invalid."
            )

        clarification = {
            "type": "switch_confirmation",
            "question": (
                "A task is waiting for your response. Do you want to "
                "continue it or switch to the new request?"
            ),
            "options": [
                "continue_current_task",
                "switch_to_new_request",
            ],
        }
        return {
            "final_response": {
                "success": True,
                "status": "switch_confirmation_required",
                "agent": waiting_agent.value,
                "answer": None,
                "clarification": clarification,
                "reason": reason,
                "error": None,
            },
            "error": None,
        }


def _gate_reason(
    state: MultiAgentState,
    expected_route: ConversationRoute,
) -> str | None:
    decision = state.get("gate_decision")
    if not isinstance(decision, dict):
        return None
    try:
        route = ConversationRoute(decision.get("route"))
    except (TypeError, ValueError):
        return None
    reason = decision.get("reason")
    if (
        route is not expected_route
        or decision.get("target") is not None
        or not isinstance(reason, str)
        or not reason.strip()
    ):
        return None
    return reason.strip()
