import time
import unittest

import jwt

from authentication.jwt_tokens import JWTAuthenticationError, JWTTokenVerifier


class JWTTokenVerifierTests(unittest.TestCase):
    secret = "a" * 32
    issuer = "mini-rag-agent"
    audience = "mini-rag-agent-api"

    def setUp(self):
        self.verifier = JWTTokenVerifier(
            secret=self.secret,
            algorithm="HS256",
            issuer=self.issuer,
            audience=self.audience,
        )

    def _token(self, **claims):
        now = int(time.time())
        payload = {
            "sub": "user-42",
            "roles": ["analyst", "analyst"],
            "iss": self.issuer,
            "aud": self.audience,
            "iat": now,
            "exp": now + 60,
            **claims,
        }
        return jwt.encode(payload, self.secret, algorithm="HS256")

    def test_verifies_identity_and_deduplicates_roles(self):
        principal = self.verifier.verify(self._token())

        self.assertEqual(principal.subject, "user-42")
        self.assertEqual(principal.roles, ("analyst",))

    def test_rejects_expired_token(self):
        with self.assertRaises(JWTAuthenticationError):
            self.verifier.verify(self._token(exp=int(time.time()) - 1))

    def test_rejects_wrong_audience(self):
        with self.assertRaises(JWTAuthenticationError):
            self.verifier.verify(self._token(aud="another-api"))

    def test_rejects_malformed_roles(self):
        with self.assertRaises(JWTAuthenticationError):
            self.verifier.verify(self._token(roles="admin"))

    def test_rejects_short_secret_at_configuration_time(self):
        with self.assertRaises(ValueError):
            JWTTokenVerifier(
                secret="short-secret",
                algorithm="HS256",
                issuer=self.issuer,
                audience=self.audience,
            )


if __name__ == "__main__":
    unittest.main()
