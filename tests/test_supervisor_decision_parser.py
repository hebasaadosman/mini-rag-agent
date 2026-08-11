import unittest

from agents.multi_agent import (
    SupervisorDecisionParseError,
    SupervisorDecisionParser,
    SupervisorReason,
    SupervisorRoute,
)


class SupervisorDecisionParserTests(unittest.TestCase):
    def test_parses_plain_json(self):
        decision = SupervisorDecisionParser.parse(
            {
                "content": (
                    '{"route":"knowledge",'
                    '"reason":"project_knowledge",'
                    '"confidence":0.95}'
                )
            }
        )

        self.assertEqual(decision.route, SupervisorRoute.KNOWLEDGE)
        self.assertEqual(
            decision.reason,
            SupervisorReason.PROJECT_KNOWLEDGE,
        )

    def test_parses_json_code_fence(self):
        decision = SupervisorDecisionParser.parse(
            {
                "content": (
                    "```json\n"
                    '{"route":"utility",'
                    '"reason":"external_information",'
                    '"confidence":0.82}\n'
                    "```"
                )
            }
        )

        self.assertEqual(decision.route, SupervisorRoute.UTILITY)

    def test_parses_clarification_decision(self):
        decision = SupervisorDecisionParser.parse(
            {
                "content": (
                    '{"route":"clarification",'
                    '"reason":"ambiguous_request",'
                    '"confidence":0.45,'
                    '"clarification_question":"Which service?"}'
                )
            }
        )

        self.assertEqual(
            decision.clarification_question,
            "Which service?",
        )

    def test_rejects_invalid_json_without_echoing_content(self):
        sensitive_content = "secret-value {not-json"

        with self.assertRaises(
            SupervisorDecisionParseError
        ) as context:
            SupervisorDecisionParser.parse(
                {"content": sensitive_content}
            )

        self.assertNotIn(
            sensitive_content,
            str(context.exception),
        )

    def test_rejects_json_array(self):
        with self.assertRaises(SupervisorDecisionParseError):
            SupervisorDecisionParser.parse(
                {"content": '["knowledge"]'}
            )

    def test_rejects_decision_that_breaks_the_schema(self):
        with self.assertRaises(SupervisorDecisionParseError):
            SupervisorDecisionParser.parse(
                {
                    "content": (
                        '{"route":"knowledge",'
                        '"reason":"external_information",'
                        '"confidence":0.95}'
                    )
                }
            )

    def test_rejects_missing_content(self):
        for response in ({}, {"content": "   "}):
            with self.subTest(response=response):
                with self.assertRaises(
                    SupervisorDecisionParseError
                ):
                    SupervisorDecisionParser.parse(response)


if __name__ == "__main__":
    unittest.main()
