import asyncio
import json
from collections.abc import Callable
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


JsonRequester = Callable[
    [str, dict[str, Any], float],
    dict[str, Any],
]


class LocationNotFoundError(ValueError):
    pass


class OpenMeteoClient:
    GEOCODING_URL = (
        "https://geocoding-api.open-meteo.com/v1/search"
    )
    FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
    MAX_RESPONSE_BYTES = 1_000_000

    def __init__(
        self,
        *,
        requester: JsonRequester | None = None,
        timeout_seconds: float = 8,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive.")

        self._requester = requester or self._request_json
        self._timeout_seconds = timeout_seconds

    async def resolve_location(
        self,
        location: str,
        *,
        language: str = "en",
    ) -> dict[str, Any]:
        normalized_location = self._normalize_location(location)
        normalized_language = self._normalize_language(language)
        payload = await self._get_json(
            self.GEOCODING_URL,
            {
                "name": normalized_location,
                "count": 1,
                "format": "json",
                "language": normalized_language,
            },
        )

        results = payload.get("results")
        if not isinstance(results, list) or not results:
            raise LocationNotFoundError(
                f"No location matched '{normalized_location}'."
            )

        result = results[0]
        if not isinstance(result, dict):
            raise RuntimeError("The geocoding response is invalid.")

        try:
            latitude = float(result["latitude"])
            longitude = float(result["longitude"])
            timezone = str(result["timezone"])
            name = str(result["name"])
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError(
                "The geocoding response is incomplete."
            ) from exc

        return {
            "name": name,
            "country": str(result.get("country") or ""),
            "country_code": str(result.get("country_code") or ""),
            "latitude": latitude,
            "longitude": longitude,
            "timezone": timezone,
        }

    async def get_current_weather(
        self,
        location: str,
        *,
        language: str = "en",
    ) -> dict[str, Any]:
        resolved = await self.resolve_location(
            location,
            language=language,
        )
        payload = await self._get_json(
            self.FORECAST_URL,
            {
                "latitude": resolved["latitude"],
                "longitude": resolved["longitude"],
                "current": (
                    "temperature_2m,relative_humidity_2m,"
                    "apparent_temperature,precipitation,"
                    "weather_code,wind_speed_10m,is_day"
                ),
                "timezone": "auto",
            },
        )

        current = payload.get("current")
        units = payload.get("current_units")
        if not isinstance(current, dict) or not isinstance(units, dict):
            raise RuntimeError("The weather response is incomplete.")

        observed_at = str(current.get("time") or "").strip()
        if not observed_at:
            raise RuntimeError(
                "The weather response is missing observation time."
            )

        weather_code = self._required_int(current, "weather_code")
        return {
            "location": resolved,
            "observed_at": observed_at,
            "timezone": str(
                payload.get("timezone") or resolved["timezone"]
            ),
            "temperature": self._measurement(
                current,
                units,
                "temperature_2m",
            ),
            "apparent_temperature": self._measurement(
                current,
                units,
                "apparent_temperature",
            ),
            "relative_humidity": self._measurement(
                current,
                units,
                "relative_humidity_2m",
            ),
            "precipitation": self._measurement(
                current,
                units,
                "precipitation",
            ),
            "wind_speed": self._measurement(
                current,
                units,
                "wind_speed_10m",
            ),
            "weather_code": weather_code,
            "condition": describe_wmo_weather_code(weather_code),
            "is_day": bool(self._required_int(current, "is_day")),
            "source": "Open-Meteo",
        }

    async def _get_json(
        self,
        url: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        payload = await asyncio.to_thread(
            self._requester,
            url,
            params,
            self._timeout_seconds,
        )
        if not isinstance(payload, dict):
            raise RuntimeError("The external API returned invalid JSON.")
        if payload.get("error"):
            raise RuntimeError("The external API rejected the request.")
        return payload

    @classmethod
    def _request_json(
        cls,
        url: str,
        params: dict[str, Any],
        timeout_seconds: float,
    ) -> dict[str, Any]:
        request_url = f"{url}?{urlencode(params)}"
        request = Request(
            request_url,
            headers={"User-Agent": "mini-rag-agent/1.0"},
        )
        with urlopen(request, timeout=timeout_seconds) as response:
            body = response.read(cls.MAX_RESPONSE_BYTES + 1)

        if len(body) > cls.MAX_RESPONSE_BYTES:
            raise RuntimeError("The external API response is too large.")

        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                "The external API returned invalid JSON."
            ) from exc

        if not isinstance(payload, dict):
            raise RuntimeError("The external API returned invalid JSON.")
        return payload

    @staticmethod
    def _normalize_location(location: str) -> str:
        normalized = str(location or "").strip()
        if len(normalized) < 2 or len(normalized) > 120:
            raise ValueError(
                "location must contain between 2 and 120 characters."
            )
        return normalized

    @staticmethod
    def _normalize_language(language: str) -> str:
        normalized = str(language or "en").strip().lower()
        if len(normalized) != 2 or not normalized.isalpha():
            raise ValueError("language must be a two-letter code.")
        return normalized

    @staticmethod
    def _required_int(payload: dict[str, Any], key: str) -> int:
        try:
            return int(payload[key])
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError(
                f"The weather response is missing {key}."
            ) from exc

    @staticmethod
    def _measurement(
        values: dict[str, Any],
        units: dict[str, Any],
        key: str,
    ) -> dict[str, Any]:
        try:
            value = float(values[key])
            unit = str(units[key])
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError(
                f"The weather response is missing {key}."
            ) from exc
        return {"value": value, "unit": unit}


def describe_wmo_weather_code(code: int) -> str:
    descriptions = {
        0: "clear_sky",
        1: "mainly_clear",
        2: "partly_cloudy",
        3: "overcast",
        45: "fog",
        48: "depositing_rime_fog",
        51: "light_drizzle",
        53: "moderate_drizzle",
        55: "dense_drizzle",
        56: "light_freezing_drizzle",
        57: "dense_freezing_drizzle",
        61: "slight_rain",
        63: "moderate_rain",
        65: "heavy_rain",
        66: "light_freezing_rain",
        67: "heavy_freezing_rain",
        71: "slight_snowfall",
        73: "moderate_snowfall",
        75: "heavy_snowfall",
        77: "snow_grains",
        80: "slight_rain_showers",
        81: "moderate_rain_showers",
        82: "violent_rain_showers",
        85: "slight_snow_showers",
        86: "heavy_snow_showers",
        95: "thunderstorm",
        96: "thunderstorm_with_slight_hail",
        99: "thunderstorm_with_heavy_hail",
    }
    return descriptions.get(code, "unknown")
