from abc import ABC, abstractmethod
import asyncio
from collections.abc import Callable
from typing import Any


class LLMInterface(ABC):
    @abstractmethod
    def set_generation_model(
        self,
        model_id: str,
    ):
        pass

    @abstractmethod
    def set_embedding_model(
        self,
        model_id: str,
        model_size: int | None = None,
    ):
        pass

    @abstractmethod
    def generate_text(
        self,
        prompt: str,
        chat_history: list | None = None,
        max_tokens: int = 100,
        temperature: float | None = None,
        **kwargs,
    ) -> str | None:
        pass

    @abstractmethod
    def generate_embedding(
        self,
        text,
        document_type: str | None = None,
        **kwargs,
    ) -> list | None:
        pass

    @abstractmethod
    def construct_prompt(
        self,
        prompt: str,
        role: str,
        **kwargs,
    ) -> dict:
        pass

    @abstractmethod
    def generate_tool_response(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_choice: str | dict = "auto",
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> dict[str, Any]:
        """
        Return a normalized assistant response that may contain
        text, tool calls, or both.
        """
        pass

    @abstractmethod
    def construct_assistant_tool_message(
        self,
        response: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Build the assistant message that contains
        the model's requested tool calls.
        """
        pass

    @abstractmethod
    def construct_tool_result_message(
        self,
        *,
        tool_call_id: str,
        tool_name: str,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Build the provider-specific tool-result message.
        """
        pass

    async def generate_tool_response_stream(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_choice: str | dict = "auto",
        max_tokens: int | None = None,
        temperature: float | None = None,
        on_content_delta: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        """Fallback stream adapter for providers without native streaming."""

        response = await asyncio.to_thread(
            self.generate_tool_response,
            messages=messages,
            tools=tools,
            tool_choice=tool_choice,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        content = str(response.get("content") or "")
        if content and on_content_delta is not None:
            on_content_delta(content)
        return response
