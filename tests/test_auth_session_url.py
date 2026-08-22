from types import SimpleNamespace
import unittest

from authentication.session_url import resolve_auth_session_redis_url


class AuthSessionRedisUrlTests(unittest.TestCase):
    def test_explicit_session_url_wins(self):
        settings = SimpleNamespace(
            AUTH_SESSION_REDIS_URL="redis://:session-password@redis:6379/7",
            APP_ENV="local",
            CELERY_RESULT_BACKEND="redis://:celery-password@redis:6379/0",
        )
        self.assertEqual(
            resolve_auth_session_redis_url(settings),
            "redis://:session-password@redis:6379/7",
        )

    def test_local_mode_derives_a_separate_redis_database(self):
        settings = SimpleNamespace(
            AUTH_SESSION_REDIS_URL="",
            APP_ENV="local",
            CELERY_RESULT_BACKEND="redis://:celery-password@redis:6379/0",
        )
        self.assertEqual(
            resolve_auth_session_redis_url(settings),
            "redis://:celery-password@redis:6379/1",
        )

    def test_production_requires_explicit_session_url(self):
        settings = SimpleNamespace(
            AUTH_SESSION_REDIS_URL="",
            APP_ENV="production",
            CELERY_RESULT_BACKEND="redis://:celery-password@redis:6379/0",
        )
        with self.assertRaisesRegex(RuntimeError, "required"):
            resolve_auth_session_redis_url(settings)


if __name__ == "__main__":
    unittest.main()
