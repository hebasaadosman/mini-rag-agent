import unittest

from models.db_schemes.mini_rag.database_url import (
    build_postgres_url,
)


class AlembicDatabaseUrlTests(unittest.TestCase):
    def setUp(self):
        self.environment = {
            "POSTGRES_HOST": "pgvector",
            "POSTGRES_PORT": "5432",
            "POSTGRES_USER": "mini_rag_user",
            "POSTGRES_PASSWORD": "p@ss:/word",
            "POSTGRES_DB": "mini-rag",
        }

    def test_builds_url_for_compose_database_service(self):
        url = build_postgres_url(self.environment)

        self.assertEqual(url.drivername, "postgresql+psycopg2")
        self.assertEqual(url.host, "pgvector")
        self.assertEqual(url.port, 5432)
        self.assertEqual(url.username, "mini_rag_user")
        self.assertEqual(url.password, "p@ss:/word")
        self.assertEqual(url.database, "mini-rag")

    def test_password_is_encoded_without_changing_its_value(self):
        url = build_postgres_url(self.environment)
        rendered = url.render_as_string(hide_password=False)

        self.assertIn("p%40ss%3A%2Fword", rendered)
        self.assertNotIn("p@ss:/word", rendered)

    def test_missing_variables_fail_without_exposing_values(self):
        environment = self.environment.copy()
        del environment["POSTGRES_HOST"]

        with self.assertRaisesRegex(
            RuntimeError,
            "Missing PostgreSQL environment variables: POSTGRES_HOST",
        ):
            build_postgres_url(environment)

    def test_invalid_port_is_rejected(self):
        environment = self.environment.copy()
        environment["POSTGRES_PORT"] = "not-a-port"

        with self.assertRaisesRegex(
            RuntimeError,
            "POSTGRES_PORT must be an integer",
        ):
            build_postgres_url(environment)


if __name__ == "__main__":
    unittest.main()
