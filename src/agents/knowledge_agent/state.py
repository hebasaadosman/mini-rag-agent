from typing import Any, TypedDict


class KnowledgeAgentState(
    TypedDict,
    total=False,
):
    """
    Shared state passed between LangGraph nodes.

    total=False allows the initial state to contain
    only the fields available at that moment.
    Other fields are added by the graph nodes.
    """

    # Initial request data.
    user_message: str
    system_prompt: str
    max_iterations: int

    # Conversation state sent to the LLM.
    messages: list[dict[str, Any]]

    # Internal backend audit history.
    tool_history: list[dict[str, Any]]

    # Latest normalized LLM response.
    model_response: dict[str, Any] | None

    # Tool execution results waiting to be added
    # to the conversation messages.
    pending_tool_executions: list[
        dict[str, Any]
    ]

    # Stable choices for a clarification that may be requested more than
    # once during the same interrupted turn.
    clarification_options: list[str]

    # Final output.
    answer: str | None
    used_chunk_ids: list[int]

    # Execution metadata.
    iterations: int
    finish_reason: str | None
    success: bool
    error: str | None
