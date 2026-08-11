from enum import Enum

from pydantic import ValidationError

from .schemas import SupervisorDecision
from .state import AgentName, MultiAgentState, TaskStatus


class SupervisorDestination(str, Enum):
    KNOWLEDGE = "knowledge"
    UTILITY = "utility"
    GENERAL = "general"
    EMAIL = "email"
    CLARIFICATION = "clarification"
    FAILURE = "failure"


class SupervisorRouter:
    @staticmethod
    def route(state: MultiAgentState) -> SupervisorDestination:
        if state.get("error"):
            return SupervisorDestination.FAILURE

        try:
            task_status = TaskStatus(
                state.get("task_status", TaskStatus.IDLE)
            )
        except (TypeError, ValueError):
            return SupervisorDestination.FAILURE

        if task_status == TaskStatus.FAILED:
            return SupervisorDestination.FAILURE

        raw_decision = state.get("supervisor_decision")
        if not isinstance(raw_decision, dict):
            return SupervisorDestination.FAILURE

        try:
            decision = SupervisorDecision.model_validate(raw_decision)
        except ValidationError:
            return SupervisorDestination.FAILURE

        destination = SupervisorDestination(decision.route.value)
        target_agent = {
            SupervisorDestination.KNOWLEDGE: AgentName.KNOWLEDGE,
            SupervisorDestination.UTILITY: AgentName.UTILITY,
            SupervisorDestination.GENERAL: AgentName.GENERAL,
            SupervisorDestination.EMAIL: AgentName.EMAIL,
        }.get(destination)

        raw_visited_agents = state.get("visited_agents") or []
        if not isinstance(raw_visited_agents, list):
            return SupervisorDestination.FAILURE

        try:
            visited_agents = {
                AgentName(agent)
                for agent in raw_visited_agents
            }
        except (TypeError, ValueError):
            return SupervisorDestination.FAILURE

        if target_agent is not None and target_agent in visited_agents:
            return SupervisorDestination.FAILURE

        return destination
