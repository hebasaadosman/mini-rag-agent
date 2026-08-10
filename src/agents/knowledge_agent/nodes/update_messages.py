from typing import Any

from ..state import KnowledgeAgentState


class UpdateMessagesNode:
    """
    Convert tool execution results into LLM messages.

    This node:
    - adds the assistant tool-call message
    - adds the tool-result messages
    - updates backend tool_history
    """

    def __init__(
        self,
        *,
        llm_provider,
    ) -> None:
        self._llm_provider = llm_provider

    async def __call__(
        self,
        state: KnowledgeAgentState,
    ) -> dict[str, Any]:
        model_response = (
            state.get("model_response")
            or {}
        )

        pending_executions = state.get(
            "pending_tool_executions",
            [],
        )

        updated_messages = list(
            state.get("messages", [])
        )

        updated_tool_history = list(
            state.get("tool_history", [])
        )

        assistant_tool_message = (
            self._llm_provider
            .construct_assistant_tool_message(
                model_response
            )
        )

        updated_messages.append(
            assistant_tool_message
        )

        for execution in pending_executions:
            tool_result_message = (
                self._llm_provider
                .construct_tool_result_message(
                    tool_call_id=execution[
                        "tool_call_id"
                    ],
                    tool_name=execution[
                        "tool_name"
                    ],
                    result=execution[
                        "execution_result"
                    ],
                )
            )

            updated_messages.append(
                tool_result_message
            )

            updated_tool_history.append(
                execution
            )
           
        return {
            "messages": updated_messages,
            "tool_history": (
                updated_tool_history
            ),
            "pending_tool_executions": [],
            "model_response": None,
        }