from typing import Any

from .BaseTool import BaseTool
from .OpenMeteoClient import OpenMeteoClient


class GetCurrentWeatherTool(BaseTool):
    name = "get_current_weather"
    description = (
        "Get current weather conditions for a city or location. "
        "Use this tool for live weather; never guess current conditions."
    )

    def __init__(self, client: OpenMeteoClient | None = None) -> None:
        self._client = client or OpenMeteoClient()

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
                        "location": {
                            "type": "string",
                            "description": (
                                "City or location, optionally with country."
                            ),
                        },
                        "language": {
                            "type": "string",
                            "description": (
                                "Two-letter response language code."
                            ),
                            "default": "en",
                        },
                    },
                    "required": ["location"],
                    "additionalProperties": False,
                },
            },
        }

    async def execute(
        self,
        *,
        location: str,
        language: str = "en",
    ) -> dict[str, Any]:
        return await self._client.get_current_weather(
            location,
            language=language,
        )
