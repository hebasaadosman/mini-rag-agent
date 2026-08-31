from types import SimpleNamespace
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from helpers.cors import configure_browser_cors


class BrowserCorsTests(unittest.TestCase):
    def test_credentialed_cors_allows_only_the_configured_spa_origin(self):
        app = FastAPI()
        configure_browser_cors(
            app,
            SimpleNamespace(CORS_ALLOWED_ORIGINS=["http://127.0.0.1:4200"]),
        )

        @app.post("/api/v1/projects")
        async def create_project():
            return {"ok": True}

        client = TestClient(app)
        preflight = client.options(
            "/api/v1/projects",
            headers={
                "Origin": "http://127.0.0.1:4200",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "X-CSRF-Token, Content-Type",
            },
        )
        self.assertEqual(preflight.status_code, 200)
        self.assertEqual(preflight.headers["access-control-allow-origin"], "http://127.0.0.1:4200")
        self.assertEqual(preflight.headers["access-control-allow-credentials"], "true")
        self.assertIn("X-CSRF-Token", preflight.headers["access-control-allow-headers"])

        denied = client.options(
            "/api/v1/projects",
            headers={
                "Origin": "http://localhost:4200",
                "Access-Control-Request-Method": "POST",
            },
        )
        self.assertIsNone(denied.headers.get("access-control-allow-origin"))
