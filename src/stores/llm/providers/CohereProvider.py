import asyncio
import logging
from collections.abc import Callable, Iterator
from typing import Any, List, Union
import json
import cohere

from ..LLMEnum import CohereRoleEnum, DocumentTypeEnum
from ..LLMInterface import LLMInterface


class CohereProvider(LLMInterface):
    def __init__(
        self,
        api_key: str,
        default_input_max_characters: int = 2000,
        default_generation_max_output_tokens: int = 100,
        default_generation_temperature: float = 0.1,
        generation_model_id: str | None = None,
    ) -> None:
        self.api_key = api_key

        self.default_input_max_characters = (
            default_input_max_characters
        )
        self.default_generation_max_output_tokens = (
            default_generation_max_output_tokens
        )
        self.default_generation_temperature = (
            default_generation_temperature
        )

        # Prefer configuring this through Settings / Factory.
        self.generation_model_id = generation_model_id

        self.embedding_model_id = "embed-multilingual-v3.0"
        self.embedding_size = 1024

        self.client = cohere.ClientV2(
            api_key=self.api_key,
        )

        self.enums = CohereRoleEnum
        self.logger = logging.getLogger(__name__)

    def set_generation_model(
        self,
        model_id: str,
    ) -> None:
        self.generation_model_id = model_id

    def set_embedding_model(
        self,
        model_id: str,
        model_size: int | None = None,
    ) -> None:
        self.embedding_model_id = model_id

        if model_size is not None:
            self.embedding_size = model_size

    def generate_text(
        self,
        prompt: str,
        chat_history: list | None = None,
        max_tokens: int = 100,
        temperature: float | None = None,
        **kwargs,
    ) -> str | None:
        if not self.client:
            self.logger.error(
                "Cohere client is not initialized."
            )
            return None

        if not self.generation_model_id:
            self.logger.error(
                "Cohere generation model ID is not configured."
            )
            return None

        if temperature is None:
            temperature = (
                self.default_generation_temperature
            )

        if max_tokens is None:
            max_tokens = (
                self.default_generation_max_output_tokens
            )

        messages = (
            list(chat_history)
            if chat_history is not None
            else []
        )

        messages.append(
            self.construct_prompt(
                prompt=prompt,
                role=CohereRoleEnum.USER.value,
            )
        )

        response = self.client.chat(
            model=self.generation_model_id,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        return self._extract_response_text(response)
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
        Generate a normalized assistant response that may
        contain text, tool calls, or both.
        """

        if not self.client:
            raise RuntimeError(
                "Cohere client is not initialized."
            )

        if not self.generation_model_id:
            raise RuntimeError(
                "Cohere generation model ID is not configured."
            )

        if temperature is None:
            temperature = (
                self.default_generation_temperature
            )

        if max_tokens is None:
            max_tokens = (
                self.default_generation_max_output_tokens
            )

        normalized_tool_choice = self._normalize_tool_choice(tool_choice)

        request_kwargs: dict[str, Any] = {
            "model": self.generation_model_id,
            "messages": messages,
            "tools": tools,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        if normalized_tool_choice is not None:
            request_kwargs["tool_choice"] = (
                normalized_tool_choice
            )

        try:
            response = self.client.chat(
                **request_kwargs,
            )

        except TypeError:
            request_kwargs.pop(
                "tool_choice",
                None,
            )

            response = self.client.chat(
                **request_kwargs,
            )

        message = getattr(
            response,
            "message",
            None,
        )

        if message is None:
            raise RuntimeError(
                "Cohere returned an invalid chat response."
            )

        normalized_tool_calls: list[dict[str, Any]] = []

        for tool_call in (
            getattr(message, "tool_calls", None) or []
        ):
            function = getattr(
                tool_call,
                "function",
                None,
            )

            if function is None:
                continue

            normalized_tool_calls.append(
                {
                    "id": getattr(
                        tool_call,
                        "id",
                        None,
                    ),
                    "type": getattr(
                        tool_call,
                        "type",
                        "function",
                    ),
                    "name": getattr(
                        function,
                        "name",
                        "",
                    ),
                    "arguments": getattr(
                        function,
                        "arguments",
                        "{}",
                    ),
                }
            )

        return {
            "content": self._extract_response_text(
                response
            ),
            "tool_calls": normalized_tool_calls,
            "finish_reason": getattr(
                response,
                "finish_reason",
                None,
            ),
        }

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
        """Stream Cohere V2 content and normalize tool-call deltas."""

        if not self.client:
            raise RuntimeError("Cohere client is not initialized.")
        if not self.generation_model_id:
            raise RuntimeError("Cohere generation model ID is not configured.")

        resolved_temperature = (
            self.default_generation_temperature
            if temperature is None
            else temperature
        )
        resolved_max_tokens = (
            self.default_generation_max_output_tokens
            if max_tokens is None
            else max_tokens
        )
        normalized_tool_choice = self._normalize_tool_choice(tool_choice)
        request_kwargs: dict[str, Any] = {
            "model": self.generation_model_id,
            "messages": messages,
            "tools": tools,
            "max_tokens": resolved_max_tokens,
            "temperature": resolved_temperature,
        }
        if normalized_tool_choice is not None:
            request_kwargs["tool_choice"] = normalized_tool_choice

        try:
            stream = await asyncio.to_thread(
                self.client.chat_stream,
                **request_kwargs,
            )
        except TypeError:
            request_kwargs.pop("tool_choice", None)
            stream = await asyncio.to_thread(
                self.client.chat_stream,
                **request_kwargs,
            )

        content_parts: list[str] = []
        tool_calls_by_index: dict[int, dict[str, Any]] = {}
        finish_reason: str | None = None
        iterator = iter(stream)

        while True:
            has_event, event = await asyncio.to_thread(
                self._next_stream_event,
                iterator,
            )
            if not has_event:
                break

            event_type = getattr(event, "type", "")
            delta = getattr(event, "delta", None)
            message = getattr(delta, "message", None)

            if event_type == "content-delta":
                content = getattr(message, "content", None)
                text = str(getattr(content, "text", "") or "")
                if text:
                    content_parts.append(text)
                    if on_content_delta is not None:
                        on_content_delta(text)
                continue

            if event_type == "tool-call-start":
                index = int(getattr(event, "index", 0) or 0)
                tool_call = getattr(message, "tool_calls", None)
                function = getattr(tool_call, "function", None)
                tool_calls_by_index[index] = {
                    "id": str(getattr(tool_call, "id", "") or ""),
                    "type": str(
                        getattr(tool_call, "type", "function")
                        or "function"
                    ),
                    "name": str(getattr(function, "name", "") or ""),
                    "arguments": str(
                        getattr(function, "arguments", "") or ""
                    ),
                }
                continue

            if event_type == "tool-call-delta":
                index = int(getattr(event, "index", 0) or 0)
                accumulated = tool_calls_by_index.setdefault(
                    index,
                    {
                        "id": "",
                        "type": "function",
                        "name": "",
                        "arguments": "",
                    },
                )
                tool_call = getattr(message, "tool_calls", None)
                function = getattr(tool_call, "function", None)
                accumulated["arguments"] += str(
                    getattr(function, "arguments", "") or ""
                )
                continue

            if event_type == "message-end":
                finish_reason = str(
                    getattr(delta, "finish_reason", "") or ""
                )

        return {
            "content": "".join(content_parts),
            "tool_calls": [
                tool_calls_by_index[index]
                for index in sorted(tool_calls_by_index)
            ],
            "finish_reason": finish_reason,
        }

    @staticmethod
    def _normalize_tool_choice(tool_choice: str | dict) -> str | dict | None:
        if not isinstance(tool_choice, str):
            return tool_choice
        return {
            "auto": None,
            "required": "REQUIRED",
            "none": "NONE",
        }.get(tool_choice.lower(), tool_choice)

    @staticmethod
    def _next_stream_event(iterator: Iterator[Any]) -> tuple[bool, Any]:
        try:
            return True, next(iterator)
        except StopIteration:
            return False, None
    def generate_embedding(
        self,
        text: Union[str, List[str]],
        document_type: str | None = None,
        **kwargs,
    ) -> list | None:
        """
        Generate document or query embeddings.

        This method is intentionally synchronous to match
        OpenAIProvider and the existing NLPController usage.
        """

        if not self.client:
            self.logger.error(
                "Cohere client is not initialized."
            )
            return None

        if not self.embedding_model_id:
            self.logger.error(
                "Cohere embedding model ID is not configured."
            )
            return None

        is_batch = isinstance(
            text,
            list,
        )

        texts = (
            text
            if is_batch
            else [text]
        )

        processed_texts = [
            self.process_text(item)
            for item in texts
        ]

        input_type = self._get_embedding_input_type(
                document_type
            )

        response = self.client.embed(
            model=self.embedding_model_id,
            texts=processed_texts,
            input_type=input_type,
            embedding_types=["float"],
        )

        embeddings_container = getattr(
            response,
            "embeddings",
            None,
        )

        embeddings = getattr(
            embeddings_container,
            "float",
            None,
        )

        if not embeddings:
            self.logger.error(
                "Cohere returned no embeddings."
            )
            return None

        return (
            embeddings
            if is_batch
            else embeddings[0]
        )

    def construct_prompt(
        self,
        prompt: str,
        role: str = CohereRoleEnum.USER.value,
        **kwargs,
    ) -> dict[str, Any]:
        """
        Cohere Chat API v2 uses content rather than the
        legacy text field.
        """

        return {
            "role": role,
            "content": prompt,
        }

    def process_text(
        self,
        text: str,
    ) -> str:
        if (
            len(text)
            > self.default_input_max_characters
        ):
            self.logger.warning(
                "Input text exceeds the Cohere character "
                "limit of %s. Truncating.",
                self.default_input_max_characters,
            )

            return text[
                :self.default_input_max_characters
            ].strip()

        return text.strip()

    @staticmethod
    def _extract_response_text(
        response: Any,
    ) -> str:
        """
        Extract text safely from a Cohere Chat API v2
        response.

        message.content is commonly a list of content blocks.
        """

        message = getattr(
            response,
            "message",
            None,
        )

        if message is None:
            return ""

        content = getattr(
            message,
            "content",
            None,
        )

        if not content:
            return ""

        if isinstance(content, str):
            return content.strip()

        text_parts: list[str] = []

        for block in content:
            block_text = getattr(
                block,
                "text",
                None,
            )

            if block_text:
                text_parts.append(
                    block_text
                )
                continue

            if isinstance(block, dict):
                value = block.get("text")

                if value:
                    text_parts.append(value)

        return "\n".join(
            text_parts
        ).strip()

    def _get_embedding_input_type(
        self,
        document_type: str | None,
    ) -> str:
        if document_type == DocumentTypeEnum.QUERY.value:
            return "search_query"

        return "search_document"



    def construct_assistant_tool_message(
        self,
        response: dict[str, Any],
    ) -> dict[str, Any]:
        tool_calls = []

        for tool_call in response.get("tool_calls") or []:
            tool_calls.append(
                {
                    "id": tool_call["id"],
                    "type": "function",
                    "function": {
                        "name": tool_call["name"],
                        "arguments": tool_call["arguments"],
                    },
                }
            )

        return {
            "role": "assistant",
            "tool_plan": response.get("content") or "",
            "tool_calls": tool_calls,
        }


    def construct_tool_result_message(
        self,
        *,
        tool_call_id: str,
        tool_name: str,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        serialized_result = json.dumps(
            result,
            ensure_ascii=False,
            default=str,
        )

        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": [
                {
                    "type": "document",
                    "document": {
                        "data": serialized_result,
                    },
                }
            ],
        }
