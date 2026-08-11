from typing import Any

from pydantic import ValidationError

from ..schemas import SupervisorDecision, SupervisorRoute
from ..state import MultiAgentState
from ..supervisor_hitl import (
    SupervisorInterruptIdFactory,
    build_supervisor_clarification_update,
)
from .terminal_nodes import FailureNode


class SupervisorClarificationNode:
    """Pause routing when the supervisor needs one user clarification."""

    def __init__(
        self,
        *,
        interrupt_id_factory: SupervisorInterruptIdFactory | None = None,
    ) -> None:
        self._interrupt_id_factory = interrupt_id_factory

    async def __call__(self, state: MultiAgentState) -> dict[str, Any]:
        try:
            decision = SupervisorDecision.model_validate(
                state.get("supervisor_decision")
            )
        except ValidationError:
            return FailureNode.build_update(
                "The supervisor clarification decision is invalid."
            )

        if decision.route is not SupervisorRoute.CLARIFICATION:
            return FailureNode.build_update(
                "The supervisor did not request clarification."
            )

        try:
            return build_supervisor_clarification_update(
                question=decision.clarification_question,
                interrupt_id_factory=self._interrupt_id_factory,
            )
        except ValueError:
            return FailureNode.build_update(
                "The supervisor clarification data is invalid."
            )
