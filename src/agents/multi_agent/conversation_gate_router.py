from enum import Enum

from .conversation_gate import ConversationRoute
from .state import AgentName, MultiAgentState


class ConversationGateDestination(str, Enum):
    SUPERVISOR = "supervisor"
    RESUME_SUPERVISOR = "resume_supervisor"
    RESUME_KNOWLEDGE = "resume_knowledge"
    RESUME_UTILITY = "resume_utility"
    RESUME_GENERAL = "resume_general"
    RESUME_EMAIL = "resume_email"
    REQUEST_SWITCH_CONFIRMATION = "request_switch_confirmation"
    REJECTION = "rejection"
    FAILURE = "failure"


class ConversationGateRouter:
    """Validate a saved gate decision and select the next graph node."""

    _RESUME_DESTINATIONS = {
        AgentName.SUPERVISOR: ConversationGateDestination.RESUME_SUPERVISOR,
        AgentName.KNOWLEDGE: ConversationGateDestination.RESUME_KNOWLEDGE,
        AgentName.UTILITY: ConversationGateDestination.RESUME_UTILITY,
        AgentName.GENERAL: ConversationGateDestination.RESUME_GENERAL,
        AgentName.EMAIL: ConversationGateDestination.RESUME_EMAIL,
    }

    @classmethod
    def route(cls, state: MultiAgentState) -> ConversationGateDestination:
        if state.get("error"):
            return ConversationGateDestination.FAILURE

        raw_decision = state.get("gate_decision")
        if not isinstance(raw_decision, dict):
            return ConversationGateDestination.FAILURE

        try:
            route = ConversationRoute(raw_decision.get("route"))
        except (TypeError, ValueError):
            return ConversationGateDestination.FAILURE

        target = raw_decision.get("target")
        reason = raw_decision.get("reason")

        if route is ConversationRoute.SUPERVISOR:
            if target is not None or reason is not None:
                return ConversationGateDestination.FAILURE
            return ConversationGateDestination.SUPERVISOR

        if route is ConversationRoute.RESUME_TARGET:
            if reason is not None:
                return ConversationGateDestination.FAILURE
            try:
                normalized_target = AgentName(target)
            except (TypeError, ValueError):
                return ConversationGateDestination.FAILURE
            return cls._RESUME_DESTINATIONS.get(
                normalized_target,
                ConversationGateDestination.FAILURE,
            )

        if route in {
            ConversationRoute.REQUEST_SWITCH_CONFIRMATION,
            ConversationRoute.REJECT,
        }:
            if (
                target is not None
                or not isinstance(reason, str)
                or not reason.strip()
            ):
                return ConversationGateDestination.FAILURE
            if route is ConversationRoute.REQUEST_SWITCH_CONFIRMATION:
                return (
                    ConversationGateDestination.REQUEST_SWITCH_CONFIRMATION
                )
            return ConversationGateDestination.REJECTION

        return ConversationGateDestination.FAILURE
