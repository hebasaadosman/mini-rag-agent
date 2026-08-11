import json
from json import JSONDecodeError
from typing import Any

from pydantic import ValidationError

from .email_schemas import EmailModelResponse


class EmailResponseParseError(ValueError):
    pass


class EmailResponseParser:
    @classmethod
    def parse(cls, content: Any) -> EmailModelResponse:
        if not isinstance(content, str) or not content.strip():
            raise EmailResponseParseError(
                "The email specialist response has no text content."
            )

        cleaned = cls._strip_code_fence(content)
        try:
            parsed = json.loads(cleaned)
        except JSONDecodeError:
            raise EmailResponseParseError(
                "The email specialist returned invalid JSON."
            ) from None

        if not isinstance(parsed, dict):
            raise EmailResponseParseError(
                "The email specialist JSON must be an object."
            )
        try:
            return EmailModelResponse.model_validate(parsed)
        except ValidationError:
            raise EmailResponseParseError(
                "The email specialist response does not match the schema."
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
