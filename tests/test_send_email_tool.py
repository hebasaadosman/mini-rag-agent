import asyncio
import unittest

from agents.tools import SendEmailTool


class _FakeEmailGateway:
    def __init__(self, *, result=None, error=None):
        self.result = result or {"message_id": "message-123"}
        self.error = error
        self.calls = []

    async def send_email(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.result


class SendEmailToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_sends_the_exact_validated_email(self):
        gateway = _FakeEmailGateway()
        tool = SendEmailTool(gateway)

        result = await tool.execute(
            recipient="user@example.com",
            subject="  Subject  ",
            body="  Body  ",
            idempotency_key="approval-123",
        )

        self.assertEqual(
            gateway.calls,
            [
                {
                    "recipient": "user@example.com",
                    "subject": "Subject",
                    "body": "Body",
                    "idempotency_key": "approval-123",
                }
            ],
        )
        self.assertEqual(result["message_id"], "message-123")
        self.assertFalse(result["replayed"])

    async def test_same_approval_id_is_delivered_once(self):
        gateway = _FakeEmailGateway()
        tool = SendEmailTool(gateway)
        arguments = {
            "recipient": "user@example.com",
            "subject": "Subject",
            "body": "Body",
            "idempotency_key": "approval-123",
        }

        first, second = await asyncio.gather(
            tool.execute(**arguments),
            tool.execute(**arguments),
        )

        self.assertEqual(len(gateway.calls), 1)
        self.assertFalse(first["replayed"])
        self.assertTrue(second["replayed"])
        self.assertEqual(first["message_id"], second["message_id"])

    async def test_invalid_input_never_reaches_gateway(self):
        invalid_arguments = [
            {
                "recipient": "attacker@example.com\nBcc:x@example.com",
                "subject": "Subject",
                "body": "Body",
                "idempotency_key": "approval-123",
            },
            {
                "recipient": "user@example.com",
                "subject": "Subject\nBcc: attacker@example.com",
                "body": "Body",
                "idempotency_key": "approval-123",
            },
            {
                "recipient": "user@example.com",
                "subject": "Subject",
                "body": "Body",
                "idempotency_key": "short",
            },
        ]

        for arguments in invalid_arguments:
            with self.subTest(arguments=arguments):
                gateway = _FakeEmailGateway()
                tool = SendEmailTool(gateway)
                with self.assertRaises(ValueError):
                    await tool.execute(**arguments)
                self.assertEqual(gateway.calls, [])

    async def test_same_approval_id_rejects_a_different_draft(self):
        gateway = _FakeEmailGateway()
        tool = SendEmailTool(gateway)
        await tool.execute(
            recipient="user@example.com",
            subject="First",
            body="Body",
            idempotency_key="approval-123",
        )

        with self.assertRaisesRegex(ValueError, "different draft"):
            await tool.execute(
                recipient="attacker@example.com",
                subject="Changed",
                body="Changed body",
                idempotency_key="approval-123",
            )

        self.assertEqual(len(gateway.calls), 1)

    async def test_gateway_must_return_a_message_id(self):
        gateway = _FakeEmailGateway(result={"accepted": True})
        tool = SendEmailTool(gateway)

        with self.assertRaises(RuntimeError):
            await tool.execute(
                recipient="user@example.com",
                subject="Subject",
                body="Body",
                idempotency_key="approval-123",
            )

    def test_schema_is_closed_and_requires_backend_approval_id(self):
        tool = SendEmailTool(_FakeEmailGateway())
        parameters = tool.schema["function"]["parameters"]

        self.assertFalse(parameters["additionalProperties"])
        self.assertIn("idempotency_key", parameters["required"])


if __name__ == "__main__":
    unittest.main()
