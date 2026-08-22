from types import SimpleNamespace
import unittest

from helpers.config import ensure_production_authorization_enabled


class ProductionAuthorizationGuardTests(unittest.TestCase):
    def test_production_rejects_disabled_authorization(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "AUTHZ_ENABLED"):
            ensure_production_authorization_enabled(
                SimpleNamespace(APP_ENV="production", AUTHZ_ENABLED=False)
            )

    def test_non_production_allows_explicit_development_mode(self) -> None:
        ensure_production_authorization_enabled(
            SimpleNamespace(APP_ENV="local", AUTHZ_ENABLED=False)
        )

    def test_production_allows_enabled_authorization(self) -> None:
        ensure_production_authorization_enabled(
            SimpleNamespace(APP_ENV="production", AUTHZ_ENABLED=True)
        )


if __name__ == "__main__":
    unittest.main()
