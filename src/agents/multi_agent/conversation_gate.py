from dataclasses import dataclass
from enum import Enum

from .state import AgentName, MultiAgentState, TaskStatus


class ConversationEvent(str, Enum):
    NEW_MESSAGE = "new_message"
    RESUME = "resume"


class ConversationRoute(str, Enum):
    SUPERVISOR = "supervisor"
    RESUME_TARGET = "resume_target"
    REQUEST_SWITCH_CONFIRMATION = "request_switch_confirmation"
    CONTINUE_CURRENT_TASK = "continue_current_task"
    SWITCH_TO_NEW_REQUEST = "switch_to_new_request"
    REJECT = "reject"


@dataclass(frozen=True)
class ConversationGateDecision:
    route: ConversationRoute
    target: AgentName | None = None
    reason: str | None = None


class ConversationGateStateError(ValueError):
    """Raised when a checkpoint contains an invalid pending-task state."""


class ConversationGateEventError(ValueError):
    """Raised when the gate receives an unsupported conversation event."""


class ConversationGate:
    @staticmethod
    def decide(
        state: MultiAgentState,
        event: ConversationEvent,
    ) -> ConversationGateDecision:
        try:
            normalized_event = ConversationEvent(event)
        except (TypeError, ValueError) as exc:
            raise ConversationGateEventError(
                "Unsupported conversation event."
            ) from exc

        try:
            task_status = TaskStatus(
                state.get("task_status", TaskStatus.IDLE)
            )
        except (TypeError, ValueError) as exc:
            raise ConversationGateStateError(
                "The checkpoint contains an invalid task_status."
            ) from exc

        is_waiting = task_status == TaskStatus.WAITING_FOR_USER

        if is_waiting:
            resume_target = ConversationGate._validate_pending_task(state)

            if (
                normalized_event == ConversationEvent.RESUME
                and state.get("switch_confirmation_pending") is True
            ):
                switch_decision = str(
                    state.get("pending_user_message") or ""
                ).strip().casefold()
                if switch_decision == "continue_current_task":
                    return ConversationGateDecision(
                        route=ConversationRoute.CONTINUE_CURRENT_TASK,
                        target=resume_target,
                    )
                if switch_decision == "switch_to_new_request":
                    return ConversationGateDecision(
                        route=ConversationRoute.SWITCH_TO_NEW_REQUEST,
                    )
                return ConversationGateDecision(
                    route=(
                        ConversationRoute.REQUEST_SWITCH_CONFIRMATION
                    ),
                    reason=(
                        "Choose continue_current_task or "
                        "switch_to_new_request."
                    ),
                )

            if normalized_event == ConversationEvent.RESUME:
                return ConversationGateDecision(
                    route=ConversationRoute.RESUME_TARGET,
                    target=resume_target,
                )

            return ConversationGateDecision(
                route=ConversationRoute.REQUEST_SWITCH_CONFIRMATION,
                reason="A task is waiting for the user's response.",
            )

        if (
            task_status == TaskStatus.RUNNING
            and state.get("active_agent") is not None
        ):
            return ConversationGateDecision(
                route=ConversationRoute.REJECT,
                reason="The active task is still running.",
            )

        if normalized_event == ConversationEvent.RESUME:
            return ConversationGateDecision(
                route=ConversationRoute.REJECT,
                reason="No task is waiting for a response.",
            )

        return ConversationGateDecision(
            route=ConversationRoute.SUPERVISOR,
        )

    @staticmethod
    def _validate_pending_task(state: MultiAgentState) -> AgentName:
        if state.get("pending_interrupt") is None:
            raise ConversationGateStateError(
                "A waiting task must contain pending_interrupt."
            )

        resume_target = state.get("resume_target")
        if resume_target is None:
            raise ConversationGateStateError(
                "A waiting task must contain resume_target."
            )

        try:
            return AgentName(resume_target)
        except (TypeError, ValueError) as exc:
            raise ConversationGateStateError(
                "A waiting task contains an invalid resume_target."
            ) from exc
