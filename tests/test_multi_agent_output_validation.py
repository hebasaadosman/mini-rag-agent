import unittest

from validation import MultiAgentOutputContractError, MultiAgentOutputValidator


class MultiAgentOutputValidatorTests(unittest.TestCase):
    def test_completed_response_with_answer_is_valid(self):
        MultiAgentOutputValidator.validate(
            {
                "success": True,
                "status": "completed",
                "agent": "general",
                "answer": "Hello.",
                "error": None,
            }
        )

    def test_completed_response_without_answer_is_rejected(self):
        with self.assertRaises(MultiAgentOutputContractError):
            MultiAgentOutputValidator.validate(
                {
                    "success": True,
                    "status": "completed",
                    "agent": "general",
                    "answer": " ",
                    "error": None,
                }
            )

    def test_clarification_requires_question(self):
        with self.assertRaises(MultiAgentOutputContractError):
            MultiAgentOutputValidator.validate(
                {
                    "success": True,
                    "status": "clarification_required",
                    "clarification": {"options": []},
                    "error": None,
                }
            )

    def test_approval_requires_complete_draft(self):
        with self.assertRaises(MultiAgentOutputContractError):
            MultiAgentOutputValidator.validate(
                {
                    "success": True,
                    "status": "approval_required",
                    "draft": {"to": "user@example.com", "subject": "Hi"},
                    "error": None,
                }
            )

    def test_failed_response_requires_error(self):
        with self.assertRaises(MultiAgentOutputContractError):
            MultiAgentOutputValidator.validate(
                {"success": False, "status": "failed", "error": " "}
            )

    def test_message_id_is_limited_to_email_agent(self):
        with self.assertRaises(MultiAgentOutputContractError):
            MultiAgentOutputValidator.validate(
                {
                    "success": True,
                    "status": "completed",
                    "agent": "utility",
                    "answer": "It is 09:00.",
                    "message_id": "unexpected",
                    "error": None,
                }
            )


if __name__ == "__main__":
    unittest.main()
