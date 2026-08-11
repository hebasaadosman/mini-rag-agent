import json
from json import JSONDecodeError
from typing import Any

from pydantic import ValidationError

from .specialist_schemas import SpecialistResponse


class SpecialistResponseParseError(ValueError):
    pass


class SpecialistResponseParser:
    @classmethod
    def parse(cls, content: Any) -> SpecialistResponse:
        if not isinstance(content, str) or not content.strip():
            raise SpecialistResponseParseError(
                "The specialist response has no text content."
            )

        cleaned_content = cls._strip_code_fence(content)
        try:
            parsed = json.loads(cleaned_content)
        except JSONDecodeError:
            raise SpecialistResponseParseError(
                "The specialist returned invalid JSON."
            ) from None

        if not isinstance(parsed, dict):
            raise SpecialistResponseParseError(
                "The specialist JSON must be an object."
            )

        try:
            return SpecialistResponse.model_validate(parsed)
        except ValidationError:
            raise SpecialistResponseParseError(
                "The specialist response does not match the schema."
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
