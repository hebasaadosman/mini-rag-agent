from typing import Any

from ..state import KnowledgeAgentState


class BuildStateNode:
    """
    Build the first complete agent state.

    Input:
        user_message
        system_prompt
        max_iterations

    Output:
        initialized messages and runtime fields
    """

    def __init__(
        self,
        *,
        llm_provider,
        max_memory_messages: int = 40,
    ) -> None:
        self._llm_provider = llm_provider
        self._max_memory_messages = max_memory_messages

    async def __call__(
        self,
        state: KnowledgeAgentState,
    ) -> dict[str, Any]:
        user_message = (
            state.get("user_message")
            or ""
        ).strip()

        system_prompt = (
            state.get("system_prompt")
            or ""
        ).strip()

        if not user_message:
            return {
                "success": False,
                "error": (
                    "user_message cannot be empty."
                ),
            }

        if not system_prompt:
            return {
                "success": False,
                "error": (
                    "system_prompt cannot be empty."
                ),
            }

        messages = self._build_messages(
            existing_messages=state.get("messages") or [],
            system_prompt=system_prompt,
            user_message=user_message,
        )

        existing_tool_history = list(
            state.get("tool_history") or []
        )

        return {
            "user_message": user_message,
            "system_prompt": system_prompt,
            "messages": messages,
            "tool_history": existing_tool_history[
                -self._max_memory_messages:
            ],
            "model_response": None,
            "pending_tool_executions": [],
            "clarification_options": [],
            "answer": None,
            "used_chunk_ids": [],
            "iterations": 0,
            "finish_reason": None,
            "success": False,
            "error": None,
        }

    def _build_messages(
        self,
        *,
        existing_messages: list[dict[str, Any]],
        system_prompt: str,
        user_message: str,
    ) -> list[dict[str, Any]]:
        system_message = self._llm_provider.construct_prompt(
            prompt=system_prompt,
            role=self._llm_provider.enums.SYSTEM.value,
        )
        user_role = self._llm_provider.enums.USER.value
        user_message_record = self._llm_provider.construct_prompt(
            prompt=user_message,
            role=user_role,
        )

        if not existing_messages:
            return [system_message, user_message_record]

        conversation = list(existing_messages)
        if conversation and conversation[0].get("role") in {
            "system",
            "SYSTEM",
        }:
            conversation = conversation[1:]

        # Reserve slots for the system prompt, the new user
        # message, and the final assistant answer. Start at a
        # user boundary so a tool result is never retained
        # without its turn.
        retained_limit = max(self._max_memory_messages - 3, 0)
        conversation = conversation[-retained_limit:]
        while conversation and conversation[0].get("role") != user_role:
            conversation.pop(0)

        return [
            system_message,
            *conversation,
            user_message_record,
        ]
