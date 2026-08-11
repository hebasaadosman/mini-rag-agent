import unittest
from datetime import datetime

from agents.tools import (
    GetCurrentTimeTool,
    GetCurrentWeatherTool,
    LocationNotFoundError,
    OpenMeteoClient,
    describe_wmo_weather_code,
)


class _FakeRequester:
    def __init__(self, *, geocoding=None, weather=None):
        self.geocoding = geocoding or {}
        self.weather = weather or {}
        self.calls = []

    def __call__(self, url, params, timeout):
        self.calls.append(
            {"url": url, "params": params, "timeout": timeout}
        )
        if "geocoding-api" in url:
            return self.geocoding
        return self.weather


def _riyadh_location():
    return {
        "results": [
            {
                "name": "Riyadh",
                "country": "Saudi Arabia",
                "country_code": "SA",
                "latitude": 24.6877,
                "longitude": 46.7219,
                "timezone": "Asia/Riyadh",
            }
        ]
    }


class UtilityToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_weather_tool_returns_current_structured_conditions(self):
        requester = _FakeRequester(
            geocoding=_riyadh_location(),
            weather={
                "timezone": "Asia/Riyadh",
                "current": {
                    "time": "2026-08-11T15:00",
                    "temperature_2m": 41.2,
                    "relative_humidity_2m": 15,
                    "apparent_temperature": 39.8,
                    "precipitation": 0,
                    "weather_code": 0,
                    "wind_speed_10m": 18.4,
                    "is_day": 1,
                },
                "current_units": {
                    "temperature_2m": "°C",
                    "relative_humidity_2m": "%",
                    "apparent_temperature": "°C",
                    "precipitation": "mm",
                    "wind_speed_10m": "km/h",
                },
            },
        )
        tool = GetCurrentWeatherTool(
            OpenMeteoClient(requester=requester)
        )

        result = await tool.execute(location="Riyadh")

        self.assertEqual(result["location"]["timezone"], "Asia/Riyadh")
        self.assertEqual(result["temperature"]["value"], 41.2)
        self.assertEqual(result["temperature"]["unit"], "°C")
        self.assertEqual(result["condition"], "clear_sky")
        self.assertTrue(result["is_day"])
        self.assertEqual(result["source"], "Open-Meteo")
        self.assertEqual(len(requester.calls), 2)
        self.assertIn(
            "temperature_2m",
            requester.calls[1]["params"]["current"],
        )
        self.assertEqual(
            requester.calls[1]["params"]["timezone"],
            "auto",
        )

    async def test_time_tool_uses_the_resolved_iana_timezone(self):
        requester = _FakeRequester(geocoding=_riyadh_location())
        client = OpenMeteoClient(requester=requester)

        def fixed_now(timezone):
            return datetime(2026, 8, 11, 16, 30, tzinfo=timezone)

        tool = GetCurrentTimeTool(
            client,
            now_provider=fixed_now,
        )

        result = await tool.execute(location="Riyadh")

        self.assertEqual(result["timezone"], "Asia/Riyadh")
        self.assertEqual(
            result["local_time"],
            "2026-08-11T16:30:00+03:00",
        )
        self.assertEqual(result["utc_offset"], "+03:00")
        self.assertEqual(result["source"], "system_clock")

    async def test_location_not_found_is_explicit(self):
        client = OpenMeteoClient(
            requester=_FakeRequester(geocoding={"results": []})
        )

        with self.assertRaises(LocationNotFoundError):
            await client.resolve_location("Missing City")

    async def test_invalid_location_is_rejected_before_http(self):
        requester = _FakeRequester()
        client = OpenMeteoClient(requester=requester)

        with self.assertRaises(ValueError):
            await client.resolve_location(" ")

        self.assertEqual(requester.calls, [])

    async def test_invalid_language_is_rejected(self):
        client = OpenMeteoClient(requester=_FakeRequester())

        with self.assertRaises(ValueError):
            await client.resolve_location("Riyadh", language="arabic")

    async def test_external_api_errors_are_rejected(self):
        requester = _FakeRequester(
            geocoding={"error": True, "reason": "details"}
        )
        client = OpenMeteoClient(requester=requester)

        with self.assertRaisesRegex(
            RuntimeError,
            "external API rejected",
        ):
            await client.resolve_location("Riyadh")

    async def test_weather_without_observation_time_is_rejected(self):
        requester = _FakeRequester(
            geocoding=_riyadh_location(),
            weather={"timezone": "Asia/Riyadh", "current": {}, "current_units": {}},
        )
        client = OpenMeteoClient(requester=requester)

        with self.assertRaisesRegex(RuntimeError, "observation time"):
            await client.get_current_weather("Riyadh")

    def test_tool_schemas_require_location(self):
        for tool in (GetCurrentTimeTool(), GetCurrentWeatherTool()):
            with self.subTest(tool=tool.name):
                function = tool.schema["function"]
                self.assertEqual(function["name"], tool.name)
                self.assertEqual(
                    function["parameters"]["required"],
                    ["location"],
                )
                self.assertFalse(
                    function["parameters"]["additionalProperties"]
                )

    def test_wmo_codes_have_safe_fallback(self):
        self.assertEqual(describe_wmo_weather_code(95), "thunderstorm")
        self.assertEqual(describe_wmo_weather_code(500), "unknown")


if __name__ == "__main__":
    unittest.main()
