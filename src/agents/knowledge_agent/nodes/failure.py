from typing import Any

from ..state import KnowledgeAgentState


class FailureNode:
    """
    Produce the final safe failure state.
    """

    async def __call__(
        self,
        state: KnowledgeAgentState,
    ) -> dict[str, Any]:
        error = state.get("error")

        max_iterations_reached = (
            state.get("iterations", 0)
            >= state.get(
                "max_iterations",
                1,
            )
        )

        if not error:
            error = (
                "The agent reached the maximum "
                "number of iterations without "
                "producing a final answer."
            )

        return {
            "success": False,
            "answer": None,
            "used_chunk_ids": [],
            "finish_reason": (
                "max_iterations_reached"
                if max_iterations_reached
                else "error"
            ),
            "error": error,
        }