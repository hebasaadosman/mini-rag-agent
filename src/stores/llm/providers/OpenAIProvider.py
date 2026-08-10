import logging
from typing import Any, List, Union
import json 

from openai import OpenAI

from ..LLMEnum import OpenAIRoleEnum
from ..LLMInterface import LLMInterface


class OpenAIProvider(LLMInterface):
    def __init__(
        self,
        api_key: str,
        api_url: str | None = None,
        default_input_max_characters: int = 2000,
        default_generation_max_output_tokens: int = 100,
        default_generation_temperature: float = 0.1,
        generation_model_id: str | None = None,
    ) -> None:
        self.api_key = api_key
        self.api_url = api_url
        self.generation_model_id = generation_model_id

        self.default_input_max_characters = (
            default_input_max_characters
        )
        self.default_generation_max_output_tokens = (
            default_generation_max_output_tokens
        )
        self.default_generation_temperature = (
            default_generation_temperature
        )

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.api_url or None,
        )

        self.embedding_model_id = "text-embedding-3-small"
        self.embedding_size = 1536

        self.enums = OpenAIRoleEnum
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
        max_tokens: int | None = None,
        temperature: float | None = None,
        **kwargs,
    ) -> str | None:
        if not self.client:
            self.logger.error(
                "OpenAI client is not initialized."
            )
            return None

        if not self.generation_model_id:
            self.logger.error(
                "Generation model ID is not configured."
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
                prompt,
                role=OpenAIRoleEnum.USER.value,
            )
        )

        response = self.client.chat.completions.create(
            model=self.generation_model_id,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        if not response.choices:
            self.logger.error(
                "OpenAI returned no completion choices."
            )
            return None

        content = response.choices[0].message.content

        return content.strip() if content else ""

    def generate_embedding(
        self,
        text: Union[str, List[str]],
        document_type: str | None = None,
        **kwargs,
    ) -> list | None:
        if not self.client:
            self.logger.error(
                "OpenAI client is not initialized."
            )
            return None

        if not self.embedding_model_id:
            self.logger.error(
                "Embedding model ID is not configured."
            )
            return None

        is_batch = isinstance(text, list)

        prepared_input = (
            [
                self.process_text(item)
                for item in text
            ]
            if is_batch
            else self.process_text(text)
        )

        response = self.client.embeddings.create(
            model=self.embedding_model_id,
            input=prepared_input,
        )

        if not response.data:
            self.logger.error(
                "OpenAI returned no embeddings."
            )
            return None

        embeddings = [
            item.embedding
            for item in response.data
        ]

        return embeddings if is_batch else embeddings[0]

    def generate_tool_response(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_choice: str | dict = "auto",
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> dict[str, Any]:
        if not self.client:
            raise RuntimeError(
                "OpenAI client is not initialized."
            )

        if not self.generation_model_id:
            raise RuntimeError(
                "Generation model ID is not configured."
            )

        if temperature is None:
            temperature = (
                self.default_generation_temperature
            )

        if max_tokens is None:
            max_tokens = (
                self.default_generation_max_output_tokens
            )

        response = self.client.chat.completions.create(
            model=self.generation_model_id,
            messages=messages,
            tools=tools,
            tool_choice=tool_choice,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        if not response.choices:
            raise RuntimeError(
                "OpenAI returned no completion choices."
            )

        choice = response.choices[0]
        message = choice.message

        normalized_tool_calls = [
            {
                "id": tool_call.id,
                "type": tool_call.type,
                "name": tool_call.function.name,
                "arguments": tool_call.function.arguments,
            }
            for tool_call in message.tool_calls or []
        ]

        return {
            "content": message.content or "",
            "tool_calls": normalized_tool_calls,
            "finish_reason": choice.finish_reason,
        }

    def construct_prompt(
        self,
        prompt: str,
        role: str = OpenAIRoleEnum.USER.value,
        **kwargs,
    ) -> dict[str, str]:
        return {
            "role": role,
            "content": prompt,
        }

    def process_text(
        self,
        text: str,
    ) -> str:
        normalized_text = text.strip()

        if (
            len(normalized_text)
            > self.default_input_max_characters
        ):
            self.logger.warning(
                "Input text exceeds the maximum character "
                "limit of %s. Truncating.",
                self.default_input_max_characters,
            )

            return normalized_text[
                :self.default_input_max_characters
            ].strip()

        return normalized_text


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
            "content": response.get("content") or None,
            "tool_calls": tool_calls,
        }


    def construct_tool_result_message(
        self,
        *,
        tool_call_id: str,
        tool_name: str,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": json.dumps(
                result,
                ensure_ascii=False,
                default=str,
            ),
        }
