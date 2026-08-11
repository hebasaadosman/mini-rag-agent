from enum import Enum

from .specialist_schemas import HandoffReason
from .state import AgentName, MultiAgentState, TaskStatus


class SpecialistResultDestination(str, Enum):
    SUPERVISOR = "supervisor"
    END = "end"
    FAILURE = "failure"


class SpecialistResultRouter:
    """Route a validated specialist result to handoff, completion, or failure."""

    @staticmethod
    def route(
        state: MultiAgentState,
        *,
        expected_agent: AgentName,
    ) -> SpecialistResultDestination:
        if state.get("error"):
            return SpecialistResultDestination.FAILURE

        try:
            task_status = TaskStatus(state.get("task_status"))
            active_agent = AgentName(state.get("active_agent"))
            expected_agent = AgentName(expected_agent)
        except (TypeError, ValueError):
            return SpecialistResultDestination.FAILURE

        if (
            active_agent is AgentName.SUPERVISOR
            or active_agent is not expected_agent
        ):
            return SpecialistResultDestination.FAILURE

        if task_status is TaskStatus.FAILED:
            return SpecialistResultDestination.FAILURE

        if task_status is TaskStatus.RUNNING:
            try:
                HandoffReason(state.get("handoff_reason"))
            except (TypeError, ValueError):
                return SpecialistResultDestination.FAILURE
            if (
                state.get("supervisor_decision") is not None
                or state.get("resume_target") is not None
                or state.get("pending_interrupt") is not None
                or state.get("final_response") is not None
            ):
                return SpecialistResultDestination.FAILURE
            return SpecialistResultDestination.SUPERVISOR

        if task_status is TaskStatus.WAITING_FOR_USER:
            try:
                resume_target = AgentName(state.get("resume_target"))
            except (TypeError, ValueError):
                return SpecialistResultDestination.FAILURE
            if (
                resume_target is not expected_agent
                or not isinstance(state.get("pending_interrupt"), dict)
                or not isinstance(state.get("final_response"), dict)
            ):
                return SpecialistResultDestination.FAILURE
            return SpecialistResultDestination.END

        if task_status in {TaskStatus.COMPLETED, TaskStatus.CANCELLED}:
            if (
                state.get("resume_target") is not None
                or state.get("pending_interrupt") is not None
                or not isinstance(state.get("final_response"), dict)
            ):
                return SpecialistResultDestination.FAILURE
            return SpecialistResultDestination.END

        return SpecialistResultDestination.FAILURE
