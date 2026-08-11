from collections.abc import Callable
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .BaseTool import BaseTool
from .OpenMeteoClient import OpenMeteoClient


NowProvider = Callable[[ZoneInfo], datetime]


class GetCurrentTimeTool(BaseTool):
    name = "get_current_time"
    description = (
        "Get the current local date and time for a city or location. "
        "Use this tool for current time; never calculate it from memory."
    )

    def __init__(
        self,
        client: OpenMeteoClient | None = None,
        *,
        now_provider: NowProvider | None = None,
    ) -> None:
        self._client = client or OpenMeteoClient()
        self._now_provider = now_provider or datetime.now

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
                                "Two-letter location language code."
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
        resolved = await self._client.resolve_location(
            location,
            language=language,
        )
        try:
            timezone = ZoneInfo(resolved["timezone"])
        except (KeyError, TypeError, ZoneInfoNotFoundError) as exc:
            raise RuntimeError(
                "The location timezone is unavailable."
            ) from exc

        local_time = self._now_provider(timezone)
        utc_offset = local_time.strftime("%z")
        if len(utc_offset) == 5:
            utc_offset = f"{utc_offset[:3]}:{utc_offset[3:]}"

        return {
            "location": resolved,
            "timezone": resolved["timezone"],
            "local_time": local_time.isoformat(timespec="seconds"),
            "utc_offset": utc_offset,
            "source": "system_clock",
        }
