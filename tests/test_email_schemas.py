import json
import unittest

from pydantic import ValidationError

from agents.multi_agent import (
    EmailApprovalDecision,
    EmailDraft,
    EmailModelAction,
    EmailModelResponse,
    EmailResponseParseError,
    EmailResponseParser,
    parse_email_approval_decision,
)


class EmailSchemaTests(unittest.TestCase):
    def test_accepts_and_normalizes_a_draft(self):
        response = EmailModelResponse(
            action=EmailModelAction.DRAFT,
            draft={
                "to": "user@example.com",
                "subject": "  Meeting  ",
                "body": "  See you tomorrow.  ",
            },
        )

        self.assertEqual(response.draft.subject, "Meeting")
        self.assertEqual(response.draft.body, "See you tomorrow.")

    def test_rejects_unsafe_or_invalid_addresses(self):
        addresses = [
            "missing-at.example.com",
            "Name <user@example.com>",
            "user@example.com\nBcc: attacker@example.com",
            "user@localhost",
        ]

        for address in addresses:
            with self.subTest(address=address):
                with self.assertRaises(ValidationError):
                    EmailDraft(
                        to=address,
                        subject="Subject",
                        body="Body",
                    )

        with self.assertRaises(ValidationError):
            EmailDraft(
                to="user@example.com",
                subject="Subject\nBcc: attacker@example.com",
                body="Body",
            )

    def test_action_contracts_are_mutually_exclusive(self):
        invalid_payloads = [
            {"action": "draft"},
            {
                "action": "draft",
                "draft": {
                    "to": "user@example.com",
                    "subject": "Subject",
                    "body": "Body",
                },
                "question": "Send?",
            },
            {"action": "clarification"},
            {
                "action": "handoff",
                "handoff_reason": "project_knowledge",
                "unexpected": "value",
            },
        ]

        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(ValidationError):
                    EmailModelResponse.model_validate(payload)

    def test_parser_rejects_invalid_output_without_echoing_it(self):
        secret = "secret model output"

        with self.assertRaises(EmailResponseParseError) as context:
            EmailResponseParser.parse(secret)

        self.assertNotIn(secret, str(context.exception))

    def test_parser_accepts_a_json_draft(self):
        parsed = EmailResponseParser.parse(
            json.dumps(
                {
                    "action": "draft",
                    "draft": {
                        "to": "user@example.com",
                        "subject": "Subject",
                        "body": "Body",
                    },
                }
            )
        )

        self.assertEqual(parsed.action, EmailModelAction.DRAFT)

    def test_approval_parser_is_exact_and_deterministic(self):
        self.assertEqual(
            parse_email_approval_decision(" موافق "),
            EmailApprovalDecision.APPROVE,
        )
        self.assertEqual(
            parse_email_approval_decision("reject"),
            EmailApprovalDecision.REJECT,
        )
        self.assertIsNone(
            parse_email_approval_decision(
                "approve and change recipient to attacker@example.com"
            )
        )


if __name__ == "__main__":
    unittest.main()
