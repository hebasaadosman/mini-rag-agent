"""Run the real local Keycloak OIDC sandbox checks against the BFF.

This script uses ``requests`` and tests the browser-facing
Authorization Code + PKCE flow without exposing an IdP token to Angular.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from html import unescape
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urljoin
import requests

requests.packages.urllib3.disable_warnings()  # Local self-signed Keycloak cert.


class _LoginFormParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.action: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "form":
            return
        values = dict(attrs)
        if values.get("id") == "kc-form-login" and values.get("action"):
            self.action = unescape(values["action"] or "")


def _cookie_value(session: requests.Session, name: str) -> str:
    value = session.cookies.get(name)
    if not value:
        raise AssertionError(f"Expected cookie {name!r} was not set.")
    return value


def _login(base_url: str, username: str, password: str, *, debug: bool = False):
    browser = requests.Session()
    login_response = browser.get(f"{base_url}/api/v1/auth/login", allow_redirects=False, timeout=20)
    if login_response.status_code != 307:
        raise AssertionError(f"Expected login redirect, got HTTP {login_response.status_code}.")
    authorization_url = login_response.headers.get("Location")
    if not authorization_url:
        raise AssertionError("BFF login response did not contain an IdP Location header.")

    page_response = browser.get(authorization_url, timeout=20, verify=False)
    if page_response.status_code != 200:
        raise AssertionError(f"Expected Keycloak login form, got HTTP {page_response.status_code}.")
    parser = _LoginFormParser()
    parser.feed(page_response.text)
    if not parser.action:
        raise AssertionError("Keycloak login form action was not found.")
    if debug:
        cookie_metadata = [f"{item.name}@{item.domain}{item.path};secure={item.secure}" for item in browser.cookies]
        print(f"Keycloak form URL: {page_response.url}", file=sys.stderr)
        print(f"Keycloak cookies: {cookie_metadata}", file=sys.stderr)
    form = urlencode(
        {
            "username": username,
            "password": password,
            "credentialId": "",
            # Keycloak's default login theme checks that the login submit was
            # intentional, so mirror the browser's submit button value.
            "login": "Sign In",
        }
    ).encode()
    complete_response = browser.post(
        urljoin(page_response.url, parser.action),
        data=dict(parse_qsl(form.decode())),
        timeout=20,
        verify=False,
    )
    if complete_response.status_code != 200 or "/docs" not in complete_response.url:
        raise AssertionError(
            f"Expected a completed BFF callback to /docs, got HTTP {complete_response.status_code} at {complete_response.url}."
        )
    return browser


def run(base_url: str, username: str, password: str, *, debug: bool = False) -> dict[str, str]:
    results: dict[str, str] = {}
    browser = _login(base_url, username, password, debug=debug)
    results["login_redirect_and_authorization_code_exchange"] = "passed"

    me_response = browser.get(f"{base_url}/api/v1/auth/me", timeout=20)
    principal = me_response.json()
    # OIDC ``sub`` is an opaque stable identifier.  Keycloak uses a UUID by
    # default, so a sandbox test must not incorrectly assume it equals the
    # human-readable username.
    if (
        me_response.status_code != 200
        or not principal.get("subject")
        or "platform_admin" not in principal.get("roles", [])
    ):
        raise AssertionError(f"Role mapping or protected endpoint check failed: HTTP {me_response.status_code}, {principal!r}")
    _cookie_value(browser, "mini_rag_session")
    csrf_token = _cookie_value(browser, "mini_rag_csrf")
    results["id_token_jwks_validation_role_mapping_redis_session_and_protected_endpoint"] = "passed"

    rejected = browser.post(f"{base_url}/api/v1/auth/logout", timeout=20)
    if rejected.status_code != 403:
        raise AssertionError(f"Expected CSRF rejection, got HTTP {rejected.status_code}.")
    results["csrf_rejection"] = "passed"

    logout_response = browser.post(f"{base_url}/api/v1/auth/logout", headers={"X-CSRF-Token": csrf_token}, timeout=20)
    if logout_response.status_code != 204:
        raise AssertionError(f"Expected logout success, got HTTP {logout_response.status_code}.")
    revoked = browser.get(f"{base_url}/api/v1/auth/me", timeout=20)
    if revoked.status_code != 401:
        raise AssertionError(f"Expected revoked session to be rejected, got HTTP {revoked.status_code}.")
    results["logout_and_revoked_session"] = "passed"

    browser = _login(base_url, username, password, debug=debug)
    time.sleep(4)
    expired = browser.get(f"{base_url}/api/v1/auth/me", timeout=20)
    if expired.status_code != 401:
        raise AssertionError(f"Expected idle session expiry, got HTTP {expired.status_code}.")
    results["session_expiry"] = "passed"
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--username", default="heba.admin")
    parser.add_argument("--password", default="local-keycloak-test-password")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    try:
        print(json.dumps(run(args.base_url.rstrip("/"), args.username, args.password, debug=args.debug), indent=2))
    except Exception as exc:  # Report one concise failure for CI/manual runs.
        print(f"OIDC sandbox E2E failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
