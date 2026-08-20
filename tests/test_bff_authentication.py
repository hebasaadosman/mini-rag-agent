import asyncio
import unittest
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

from fastapi import FastAPI
from fastapi.testclient import TestClient

from authentication import CurrentPrincipal, InMemorySessionStore
from helpers.config import get_settings
from routes.auth import auth_router


class _Clock:
    def __init__(self, value=1_000): self.value = value
    def now(self): return self.value


class _FakeOIDCClient:
    def authorization_url(self, transaction):
        return f"https://idp.example.test/authorize?state={transaction.state}"
    async def exchange_code(self, *, code, transaction):
        assert code == "approved-code"; return "fake-id-token"
    async def validate_id_token(self, *, token, nonce):
        assert token == "fake-id-token" and nonce
        return CurrentPrincipal(subject="employee-42", roles=("analyst",))


def _settings(**overrides):
    values = {
        "AUTH_ENABLED": True, "APP_ENV": "test", "AUTH_MODE": "bff_oidc",
        "AUTH_DEVELOPMENT_MANUAL_TOKEN_ENABLED": False,
        "AUTH_SESSION_COOKIE_NAME": "mini_rag_session", "AUTH_CSRF_COOKIE_NAME": "mini_rag_csrf",
        "AUTH_CSRF_HEADER_NAME": "X-CSRF-Token", "AUTH_COOKIE_SECURE": False,
        "AUTH_COOKIE_SAMESITE": "lax", "AUTH_OIDC_TRANSACTION_TTL_SECONDS": 600,
        "AUTH_SESSION_ABSOLUTE_TIMEOUT_SECONDS": 28_800, "AUTH_FRONTEND_SUCCESS_URL": "/",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _test_app(store, settings=None):
    app = FastAPI()
    app.auth_session_store, app.oidc_client = store, _FakeOIDCClient()
    app.include_router(auth_router)
    app.dependency_overrides[get_settings] = lambda: settings or _settings()
    return app


class BFFAuthenticationTests(unittest.TestCase):
    def test_login_callback_creates_server_side_session_and_cookies(self):
        store = InMemorySessionStore()
        client = TestClient(_test_app(store), follow_redirects=False)
        state = parse_qs(urlparse(client.get("/api/v1/auth/login").headers["location"]).query)["state"][0]
        callback = client.get("/api/v1/auth/callback", params={"code": "approved-code", "state": state}, follow_redirects=False)
        self.assertEqual(callback.status_code, 303)
        self.assertIn("mini_rag_session", callback.headers["set-cookie"])
        self.assertIn("HttpOnly", callback.headers["set-cookie"])
        session = asyncio.run(store.get_session(client.cookies.get("mini_rag_session")))
        self.assertIsNotNone(session)
        self.assertEqual(session.subject, "employee-42")

    def test_logout_requires_csrf_then_removes_server_side_session(self):
        store = InMemorySessionStore()
        session = asyncio.run(store.create_session(subject="employee-42", roles=("analyst",)))
        client = TestClient(_test_app(store))
        client.cookies.set("mini_rag_session", session.session_id)
        client.cookies.set("mini_rag_csrf", session.csrf_token)
        self.assertEqual(client.post("/api/v1/auth/logout").status_code, 403)
        response = client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": session.csrf_token})
        self.assertEqual(response.status_code, 204)
        self.assertIsNone(asyncio.run(store.get_session(session.session_id)))

    def test_expired_session_is_rejected_by_me_endpoint(self):
        clock = _Clock()
        store = InMemorySessionStore(idle_timeout_seconds=10, absolute_timeout_seconds=20, clock=clock.now)
        session = asyncio.run(store.create_session(subject="employee-42", roles=()))
        clock.value += 21
        client = TestClient(_test_app(store)); client.cookies.set("mini_rag_session", session.session_id)
        self.assertEqual(client.get("/api/v1/auth/me").status_code, 401)

    def test_authenticated_session_exposes_principal_for_authorization(self):
        store = InMemorySessionStore()
        session = asyncio.run(store.create_session(subject="employee-42", roles=("platform_admin",)))
        client = TestClient(_test_app(store)); client.cookies.set("mini_rag_session", session.session_id)
        response = client.get("/api/v1/auth/me")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"subject": "employee-42", "roles": ["platform_admin"]})

    def test_login_state_cookie_must_match_callback_state(self):
        client = TestClient(_test_app(InMemorySessionStore()), follow_redirects=False)
        client.get("/api/v1/auth/login")
        response = client.get("/api/v1/auth/callback", params={"code": "approved-code", "state": "attacker-state"}, follow_redirects=False)
        self.assertEqual(response.status_code, 401)

    def test_development_bearer_mode_is_refused_in_production_environment(self):
        settings = _settings(
            APP_ENV="production",
            AUTH_MODE="development_bearer",
            AUTH_DEVELOPMENT_MANUAL_TOKEN_ENABLED=True,
        )
        response = TestClient(_test_app(InMemorySessionStore(), settings)).get("/api/v1/auth/me")
        self.assertEqual(response.status_code, 503)


if __name__ == "__main__":
    unittest.main()
