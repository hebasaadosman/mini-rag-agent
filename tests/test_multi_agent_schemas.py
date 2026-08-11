import unittest

from pydantic import ValidationError

from agents.multi_agent import (
    SupervisorDecision,
    SupervisorReason,
    SupervisorRoute,
)


class SupervisorDecisionTests(unittest.TestCase):
    def test_accepts_knowledge_route(self):
        decision = SupervisorDecision(
            route=SupervisorRoute.KNOWLEDGE,
            reason=SupervisorReason.PROJECT_KNOWLEDGE,
            confidence=0.95,
        )

        self.assertEqual(
            decision.route,
            SupervisorRoute.KNOWLEDGE,
        )
        self.assertIsNone(decision.clarification_question)

    def test_accepts_utility_route(self):
        decision = SupervisorDecision(
            route="utility",
            reason="external_information",
            confidence=0.82,
        )

        self.assertEqual(
            decision.route,
            SupervisorRoute.UTILITY,
        )

    def test_accepts_general_conversation_route(self):
        decision = SupervisorDecision(
            route=SupervisorRoute.GENERAL,
            reason=SupervisorReason.GENERAL_CONVERSATION,
            confidence=0.88,
        )

        self.assertEqual(
            decision.route,
            SupervisorRoute.GENERAL,
        )

    def test_accepts_email_route(self):
        decision = SupervisorDecision(
            route=SupervisorRoute.EMAIL,
            reason=SupervisorReason.ACTION_REQUIRED,
            confidence=0.91,
        )

        self.assertEqual(decision.route, SupervisorRoute.EMAIL)

    def test_clarification_route_requires_a_question(self):
        with self.assertRaises(ValidationError):
            SupervisorDecision(
                route=SupervisorRoute.CLARIFICATION,
                reason=SupervisorReason.AMBIGUOUS_REQUEST,
                confidence=0.40,
            )

    def test_route_rejects_a_mismatched_reason(self):
        with self.assertRaises(ValidationError):
            SupervisorDecision(
                route=SupervisorRoute.KNOWLEDGE,
                reason=SupervisorReason.EXTERNAL_INFORMATION,
                confidence=0.90,
            )

    def test_specialist_route_rejects_a_clarification_question(self):
        with self.assertRaises(ValidationError):
            SupervisorDecision(
                route=SupervisorRoute.KNOWLEDGE,
                reason=SupervisorReason.PROJECT_KNOWLEDGE,
                confidence=0.90,
                clarification_question="Which report?",
            )

    def test_clarification_question_is_trimmed(self):
        decision = SupervisorDecision(
            route=SupervisorRoute.CLARIFICATION,
            reason=SupervisorReason.AMBIGUOUS_REQUEST,
            confidence=0.50,
            clarification_question="  Which service do you need?  ",
        )

        self.assertEqual(
            decision.clarification_question,
            "Which service do you need?",
        )

    def test_confidence_must_be_between_zero_and_one(self):
        for invalid_confidence in (-0.01, 1.01):
            with self.subTest(confidence=invalid_confidence):
                with self.assertRaises(ValidationError):
                    SupervisorDecision(
                        route=SupervisorRoute.UTILITY,
                        reason=(
                            SupervisorReason.EXTERNAL_INFORMATION
                        ),
                        confidence=invalid_confidence,
                    )


if __name__ == "__main__":
    unittest.main()
