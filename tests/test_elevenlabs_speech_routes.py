import os
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes.agents import agents_router


class _SpeechService:
    def __init__(self):
        self.calls = []

    async def synthesize(self, text):
        self.calls.append(text)
        return b"mock-mp3"


class ElevenLabsSpeechRouteTests(unittest.TestCase):
    def setUp(self):
        self.previous_auth_enabled = os.environ.get("AUTH_ENABLED")
        self.previous_authz_enabled = os.environ.get("AUTHZ_ENABLED")
        os.environ["AUTH_ENABLED"] = "false"
        os.environ["AUTHZ_ENABLED"] = "false"
        self.app = FastAPI()
        self.service = _SpeechService()
        self.app.speech_service = self.service
        self.app.include_router(agents_router)
        self.client = TestClient(self.app)

    def tearDown(self):
        for name, previous in (
            ("AUTH_ENABLED", self.previous_auth_enabled),
            ("AUTHZ_ENABLED", self.previous_authz_enabled),
        ):
            if previous is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = previous

    def test_speech_endpoint_returns_audio_without_exposing_provider_credentials(self):
        response = self.client.post(
            "/api/v1/agents/1/speech",
            json={"text": "Hello from the assistant."},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"mock-mp3")
        self.assertEqual(response.headers["content-type"], "audio/mpeg")
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(self.service.calls, ["Hello from the assistant."])

    def test_speech_status_reports_availability_without_provider_details(self):
        response = self.client.get("/api/v1/agents/1/speech/status")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"enabled": True})

    def test_blank_speech_is_rejected_before_synthesis(self):
        response = self.client.post(
            "/api/v1/agents/1/speech",
            json={"text": "   "},
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.service.calls, [])

    def test_unconfigured_speech_returns_service_unavailable(self):
        self.app.speech_service = None
        response = self.client.post(
            "/api/v1/agents/1/speech",
            json={"text": "Hello"},
        )

        self.assertEqual(response.status_code, 503)


if __name__ == "__main__":
    unittest.main()
