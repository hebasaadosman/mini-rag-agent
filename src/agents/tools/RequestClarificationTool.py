from typing import Any

from .BaseTool import BaseTool


class RequestClarificationTool(BaseTool):
    """Schema-only tool used to request human clarification."""

    name = "request_clarification"
    description = (
        "Pause and ask the user one concise clarification question "
        "when their request is materially ambiguous."
    )

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "question": {
                            "type": "string",
                            "description": (
                                "A concise question in the user's language."
                            ),
                        },
                        "options": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "Optional short choices when known."
                            ),
                        },
                    },
                    "required": ["question"],
                    "additionalProperties": False,
                },
            },
        }

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        raise RuntimeError(
            "request_clarification is handled by the LangGraph HITL node."
        )
