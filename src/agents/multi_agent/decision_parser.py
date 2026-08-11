import json
from json import JSONDecodeError
from typing import Any

from pydantic import ValidationError

from .schemas import SupervisorDecision


class SupervisorDecisionParseError(ValueError):
    pass


class SupervisorDecisionParser:
    @classmethod
    def parse(
        cls,
        response: dict[str, Any],
    ) -> SupervisorDecision:
        if not isinstance(response, dict):
            raise SupervisorDecisionParseError(
                "The supervisor response must be an object."
            )

        content = response.get("content")
        if not isinstance(content, str) or not content.strip():
            raise SupervisorDecisionParseError(
                "The supervisor response has no text content."
            )

        cleaned_content = cls._strip_code_fence(content)

        try:
            parsed = json.loads(cleaned_content)
        except JSONDecodeError:
            raise SupervisorDecisionParseError(
                "The supervisor returned invalid JSON."
            ) from None

        if not isinstance(parsed, dict):
            raise SupervisorDecisionParseError(
                "The supervisor JSON must be an object."
            )

        try:
            return SupervisorDecision.model_validate(parsed)
        except ValidationError:
            raise SupervisorDecisionParseError(
                "The supervisor decision does not match the schema."
            ) from None

    @staticmethod
    def _strip_code_fence(content: str) -> str:
        cleaned = content.strip()
        if not cleaned.startswith("```"):
            return cleaned

        lines = cleaned.splitlines()[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]

        return "\n".join(lines).strip()
