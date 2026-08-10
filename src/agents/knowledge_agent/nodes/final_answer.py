import json
import logging
from json import JSONDecodeError
from typing import Any

from ..state import KnowledgeAgentState


logger = logging.getLogger(
    "uvicorn.error"
)


class FinalAnswerNode:
    """
    Parse and validate the final answer returned by the LLM.

    This node:
    - parses structured JSON output
    - normalizes used_chunk_ids
    - rejects chunk IDs not returned by retrieval tools
    - prepares the final Agent response
    """
    def __init__(self, *, llm_provider) -> None:
        self._llm_provider = llm_provider

    async def __call__(
        self,
        state: KnowledgeAgentState,
    ) -> dict[str, Any]:
        model_response = (
            state.get("model_response")
            or {}
        )

        raw_content = str(
            model_response.get("content")
            or ""
        ).strip()

        parsed_output = (
            self._parse_model_output(
                raw_content
            )
        )

        answer_value = parsed_output.get(
            "answer"
        )

        if isinstance(answer_value, str):
            answer = answer_value.strip()

        elif answer_value is not None:
            answer = json.dumps(
                answer_value,
                ensure_ascii=False,
                indent=2,
                default=str,
            )

        else:
            answer = (
                raw_content
                or "No answer was generated."
            ).strip()

        requested_chunk_ids = (
            self._normalize_chunk_ids(
                parsed_output.get(
                    "used_chunk_ids"
                )
                or []
            )
        )

        retrieved_chunk_ids = (
            self._collect_retrieved_chunk_ids(
                state.get(
                    "tool_history",
                    [],
                )
            )
        )

        validated_chunk_ids = [
            chunk_id
            for chunk_id in requested_chunk_ids
            if chunk_id
            in retrieved_chunk_ids
        ]

        validated_chunk_ids = list(
            dict.fromkeys(
                validated_chunk_ids
            )
        )

        grounding_error = None

        used_chunk_search = bool(
            retrieved_chunk_ids
        )

        if (
            used_chunk_search
            and not validated_chunk_ids
        ):
            grounding_error = (
                "The final answer was based on "
                "search_project_chunks but did "
                "not include a valid supporting "
                "chunk ID."
            )

            logger.warning(
                "KNOWLEDGE AGENT GROUNDING WARNING: %s",
                grounding_error,
            )

        messages = list(state.get("messages") or [])
        messages.append(
            self._llm_provider.construct_prompt(
                prompt=answer,
                role=self._llm_provider.enums.ASSISTANT.value,
            )
        )

        return {
            "answer": answer,
            "messages": messages,
            "used_chunk_ids": (
                validated_chunk_ids
            ),
            "grounding_error": (
                grounding_error
            ),
            "success": True,
            "error": None,
        }
    @classmethod
    def _parse_model_output(
        cls,
        raw_content: str,
    ) -> dict[str, Any]:
        if not raw_content:
            return {
                "answer": "",
                "used_chunk_ids": [],
            }

        cleaned_content = (
            cls._strip_code_fence(
                raw_content
            )
        )

        try:
            parsed = json.loads(
                cleaned_content
            )

        except JSONDecodeError:
            logger.warning(
                "The Knowledge Agent returned "
                "invalid final JSON output."
            )

            return {
                "answer": raw_content,
                "used_chunk_ids": [],
            }

        if not isinstance(parsed, dict):
            return {
                "answer": raw_content,
                "used_chunk_ids": [],
            }

        return {
            "answer": parsed.get(
                "answer",
                "",
            ),
            "used_chunk_ids": parsed.get(
                "used_chunk_ids",
                [],
            ),
        }

    @staticmethod
    def _strip_code_fence(
        content: str,
    ) -> str:
        cleaned = content.strip()

        if not cleaned.startswith("```"):
            return cleaned

        lines = cleaned.splitlines()

        if lines:
            lines = lines[1:]

        if (
            lines
            and lines[-1].strip() == "```"
        ):
            lines = lines[:-1]

        return "\n".join(
            lines
        ).strip()

    @staticmethod
    def _normalize_chunk_ids(
        chunk_ids: list[Any],
    ) -> list[int]:
        normalized: list[int] = []

        for chunk_id in chunk_ids:
            try:
                normalized_chunk_id = int(
                    chunk_id
                )

            except (
                TypeError,
                ValueError,
            ):
                continue

            if normalized_chunk_id < 1:
                continue

            if normalized_chunk_id in normalized:
                continue

            normalized.append(
                normalized_chunk_id
            )

        return normalized

    @staticmethod
    def _collect_retrieved_chunk_ids(
        tool_history: list[
            dict[str, Any]
        ],
    ) -> set[int]:
        retrieved_chunk_ids: set[int] = set()

        for execution in tool_history:
            if (
                execution.get("tool_name")
                != "search_project_chunks"
            ):
                continue

            execution_result = (
                execution.get(
                    "execution_result"
                )
                or {}
            )

            tool_result = (
                execution_result.get("result")
                or {}
            )

            search_results = (
                tool_result.get("results")
                or []
            )

            for search_result in search_results:
                chunk_id = search_result.get(
                    "chunk_id"
                )

                if isinstance(
                    chunk_id,
                    int,
                ):
                    retrieved_chunk_ids.add(
                        chunk_id
                    )

                    continue

                try:
                    normalized_chunk_id = int(
                        chunk_id
                    )

                except (
                    TypeError,
                    ValueError,
                ):
                    continue

                if normalized_chunk_id > 0:
                    retrieved_chunk_ids.add(
                        normalized_chunk_id
                    )

        return retrieved_chunk_ids
