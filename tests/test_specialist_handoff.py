import unittest

from pydantic import ValidationError

from agents.multi_agent import (
    AgentName,
    HandoffReason,
    SpecialistAction,
    SpecialistResponse,
    SpecialistResponseParseError,
    SpecialistResponseParser,
    TaskStatus,
    build_handoff_update,
    build_initial_multi_agent_state,
)


class SpecialistResponseTests(unittest.TestCase):
    def test_accepts_answer_handoff_and_clarification_contracts(self):
        answer = SpecialistResponse(
            action=SpecialistAction.ANSWER,
            answer="  Hello  ",
        )
        handoff = SpecialistResponse(
            action=SpecialistAction.HANDOFF,
            handoff_reason=HandoffReason.EXTERNAL_INFORMATION,
        )
        clarification = SpecialistResponse(
            action=SpecialistAction.CLARIFICATION,
            question="  Which city?  ",
            options=[" Riyadh ", "Jeddah", "Riyadh"],
        )

        self.assertEqual(answer.answer, "Hello")
        self.assertEqual(
            handoff.handoff_reason,
            HandoffReason.EXTERNAL_INFORMATION,
        )
        self.assertEqual(clarification.question, "Which city?")
        self.assertEqual(clarification.options, ["Riyadh", "Jeddah"])

    def test_rejects_mixed_or_incomplete_contracts(self):
        invalid_payloads = [
            {"action": "answer"},
            {
                "action": "answer",
                "answer": "Hello",
                "handoff_reason": "external_information",
            },
            {"action": "handoff"},
            {
                "action": "handoff",
                "answer": "Not allowed",
                "handoff_reason": "external_information",
            },
            {"action": "clarification"},
            {
                "action": "clarification",
                "question": "Which city?",
                "answer": "Riyadh",
            },
            {
                "action": "clarification",
                "question": "Which city?",
                "handoff_reason": "external_information",
            },
        ]

        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(ValidationError):
                    SpecialistResponse.model_validate(payload)

    def test_parser_accepts_json_code_fence(self):
        fence = chr(96) * 3
        response = SpecialistResponseParser.parse(
            fence
            + "json\n"
            + '{"action":"handoff","handoff_reason":"project_knowledge"}'
            + "\n"
            + fence
        )

        self.assertEqual(response.action, SpecialistAction.HANDOFF)
        self.assertEqual(
            response.handoff_reason,
            HandoffReason.PROJECT_KNOWLEDGE,
        )

    def test_parser_rejects_invalid_output_without_echoing_it(self):
        secret = "secret-model-output"

        with self.assertRaises(SpecialistResponseParseError) as context:
            SpecialistResponseParser.parse(secret)

        self.assertNotIn(secret, str(context.exception))


class HandoffUpdateTests(unittest.TestCase):
    def test_handoff_returns_to_supervisor_without_user_response(self):
        state = build_initial_multi_agent_state("Weather?")

        update = build_handoff_update(
            state,
            from_agent=AgentName.GENERAL,
            reason=HandoffReason.EXTERNAL_INFORMATION,
        )

        self.assertEqual(update["task_status"], TaskStatus.RUNNING)
        self.assertEqual(update["handoff_count"], 1)
        self.assertEqual(update["visited_agents"], [AgentName.GENERAL])
        self.assertEqual(
            update["handoff_reason"],
            HandoffReason.EXTERNAL_INFORMATION.value,
        )
        self.assertIsNone(update["supervisor_decision"])
        self.assertIsNone(update["final_response"])

    def test_visited_agents_are_normalized_and_deduplicated(self):
        state = build_initial_multi_agent_state("Request")
        state["visited_agents"] = ["general", AgentName.GENERAL]

        update = build_handoff_update(
            state,
            from_agent=AgentName.GENERAL,
            reason=HandoffReason.OUTSIDE_SPECIALIST_SCOPE,
        )

        self.assertEqual(update["visited_agents"], [AgentName.GENERAL])

    def test_handoff_limit_stops_a_loop(self):
        state = build_initial_multi_agent_state("Request")
        state["handoff_count"] = 3

        update = build_handoff_update(
            state,
            from_agent=AgentName.GENERAL,
            reason=HandoffReason.OUTSIDE_SPECIALIST_SCOPE,
            max_handoffs=3,
        )

        self.assertEqual(update["task_status"], TaskStatus.FAILED)
        self.assertEqual(
            update["error"],
            "The request exceeded the handoff limit.",
        )

    def test_corrupted_handoff_checkpoint_fails_safely(self):
        cases = [
            ("handoff_count", "invalid"),
            ("handoff_count", -1),
            ("visited_agents", "general"),
            ("visited_agents", ["unknown"]),
        ]

        for field, value in cases:
            with self.subTest(field=field, value=value):
                state = build_initial_multi_agent_state("Request")
                state[field] = value

                update = build_handoff_update(
                    state,
                    from_agent=AgentName.GENERAL,
                    reason=HandoffReason.OUTSIDE_SPECIALIST_SCOPE,
                )

                self.assertEqual(
                    update["task_status"],
                    TaskStatus.FAILED,
                )

    def test_max_handoffs_must_be_positive(self):
        with self.assertRaises(ValueError):
            build_handoff_update(
                build_initial_multi_agent_state("Request"),
                from_agent=AgentName.GENERAL,
                reason=HandoffReason.OUTSIDE_SPECIALIST_SCOPE,
                max_handoffs=0,
            )


if __name__ == "__main__":
    unittest.main()
