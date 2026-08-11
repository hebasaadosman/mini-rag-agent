import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from infrastructure.email import (
    SMTPEmailGateway,
    SMTPEmailSettings,
    create_send_email_tool,
)


class SMTPEmailSettingsTests(unittest.TestCase):
    def test_rejects_partial_credentials(self):
        with self.assertRaisesRegex(ValueError, "configured together"):
            SMTPEmailSettings(
                host="smtp.example.com",
                port=587,
                from_address="sender@example.com",
                username="sender@example.com",
            )

    def test_rejects_header_injection_in_sender(self):
        with self.assertRaisesRegex(ValueError, "plain email"):
            SMTPEmailSettings(
                host="smtp.example.com",
                port=587,
                from_address="sender@example.com\nBcc:x@example.com",
            )

    def test_rejects_credentials_without_transport_security(self):
        with self.assertRaisesRegex(ValueError, "require starttls or ssl"):
            SMTPEmailSettings(
                host="smtp.example.com",
                port=25,
                from_address="sender@example.com",
                username="smtp-user",
                password="smtp-secret",
                security="none",
            )


class SMTPEmailFactoryTests(unittest.TestCase):
    @staticmethod
    def _settings(**overrides):
        values = {
            "SMTP_ENABLED": True,
            "SMTP_HOST": "smtp.example.com",
            "SMTP_PORT": 587,
            "SMTP_USERNAME": "smtp-user",
            "SMTP_PASSWORD": "smtp-secret",
            "SMTP_FROM_ADDRESS": "sender@example.com",
            "SMTP_SECURITY": "starttls",
            "SMTP_TIMEOUT_SECONDS": 15,
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def test_disabled_email_does_not_build_a_delivery_tool(self):
        self.assertIsNone(
            create_send_email_tool(self._settings(SMTP_ENABLED=False))
        )

    def test_enabled_email_builds_a_send_email_tool(self):
        tool = create_send_email_tool(self._settings())
        self.assertEqual(tool.name, "send_email")

    def test_enabled_email_fails_fast_when_configuration_is_missing(self):
        with self.assertRaisesRegex(ValueError, "SMTP_HOST"):
            create_send_email_tool(self._settings(SMTP_HOST=None))


class SMTPEmailGatewayTests(unittest.IsolatedAsyncioTestCase):
    def _settings(self, **overrides):
        values = {
            "host": "smtp.example.com",
            "port": 587,
            "from_address": "sender@example.com",
            "username": "smtp-user",
            "password": "smtp-secret",
            "security": "starttls",
            "timeout_seconds": 12,
        }
        values.update(overrides)
        return SMTPEmailSettings(**values)

    @patch("infrastructure.email.smtp_gateway.ssl.create_default_context")
    @patch("infrastructure.email.smtp_gateway.smtplib.SMTP")
    async def test_starttls_delivery_uses_exact_message(
        self,
        smtp_class,
        create_context,
    ):
        client = MagicMock()
        smtp_class.return_value.__enter__.return_value = client
        context = create_context.return_value
        client.send_message.return_value = {}

        result = await SMTPEmailGateway(self._settings()).send_email(
            recipient="recipient@example.com",
            subject="Approved subject",
            body="Approved body",
            idempotency_key="approval-123",
        )

        smtp_class.assert_called_once_with(
            "smtp.example.com",
            587,
            timeout=12.0,
        )
        client.starttls.assert_called_once_with(context=context)
        client.login.assert_called_once_with("smtp-user", "smtp-secret")
        message = client.send_message.call_args.args[0]
        self.assertEqual(message["From"], "sender@example.com")
        self.assertEqual(message["To"], "recipient@example.com")
        self.assertEqual(message["Subject"], "Approved subject")
        self.assertEqual(message.get_content().strip(), "Approved body")
        self.assertIn("approval-123", message["Message-ID"])
        self.assertEqual(result["message_id"], message["Message-ID"])

    @patch("infrastructure.email.smtp_gateway.smtplib.SMTP_SSL")
    async def test_ssl_delivery_uses_ssl_client(self, smtp_ssl_class):
        client = MagicMock()
        smtp_ssl_class.return_value.__enter__.return_value = client
        client.send_message.return_value = {}

        await SMTPEmailGateway(
            self._settings(security="ssl", port=465)
        ).send_email(
            recipient="recipient@example.com",
            subject="Subject",
            body="Body",
            idempotency_key="approval-123",
        )

        smtp_ssl_class.assert_called_once()
        client.starttls.assert_not_called()

    @patch("infrastructure.email.smtp_gateway.smtplib.SMTP")
    async def test_refused_recipient_is_a_failure(self, smtp_class):
        client = MagicMock()
        smtp_class.return_value.__enter__.return_value = client
        client.send_message.return_value = {
            "recipient@example.com": (550, b"refused")
        }

        with self.assertRaisesRegex(RuntimeError, "refused"):
            await SMTPEmailGateway(self._settings()).send_email(
                recipient="recipient@example.com",
                subject="Subject",
                body="Body",
                idempotency_key="approval-123",
            )


if __name__ == "__main__":
    unittest.main()
