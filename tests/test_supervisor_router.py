import unittest

from agents.multi_agent import (
    SupervisorDestination,
    SupervisorRouter,
    TaskStatus,
    build_initial_multi_agent_state,
)


class SupervisorRouterTests(unittest.TestCase):
    def test_routes_every_valid_supervisor_destination(self):
        cases = [
            (
                {
                    "route": "knowledge",
                    "reason": "project_knowledge",
                    "confidence": 0.9,
                },
                SupervisorDestination.KNOWLEDGE,
            ),
            (
                {
                    "route": "utility",
                    "reason": "external_information",
                    "confidence": 0.8,
                },
                SupervisorDestination.UTILITY,
            ),
            (
                {
                    "route": "general",
                    "reason": "general_conversation",
                    "confidence": 0.7,
                },
                SupervisorDestination.GENERAL,
            ),
            (
                {
                    "route": "email",
                    "reason": "action_required",
                    "confidence": 0.95,
                },
                SupervisorDestination.EMAIL,
            ),
            (
                {
                    "route": "clarification",
                    "reason": "ambiguous_request",
                    "confidence": 0.6,
                    "clarification_question": "Which service do you mean?",
                },
                SupervisorDestination.CLARIFICATION,
            ),
        ]

        for decision, expected in cases:
            with self.subTest(route=decision["route"]):
                state = build_initial_multi_agent_state("Request")
                state["supervisor_decision"] = decision

                self.assertEqual(
                    SupervisorRouter.route(state),
                    expected,
                )

    def test_missing_decision_routes_to_failure(self):
        state = build_initial_multi_agent_state("Request")

        self.assertEqual(
            SupervisorRouter.route(state),
            SupervisorDestination.FAILURE,
        )

    def test_invalid_decision_routes_to_failure(self):
        state = build_initial_multi_agent_state("Request")
        state["supervisor_decision"] = {
            "route": "knowledge",
            "reason": "external_information",
            "confidence": 0.9,
        }

        self.assertEqual(
            SupervisorRouter.route(state),
            SupervisorDestination.FAILURE,
        )

    def test_existing_error_routes_to_failure(self):
        state = build_initial_multi_agent_state("Request")
        state["error"] = "Supervisor failed"

        self.assertEqual(
            SupervisorRouter.route(state),
            SupervisorDestination.FAILURE,
        )

    def test_cannot_route_back_to_an_already_tried_specialist(self):
        state = build_initial_multi_agent_state("Weather?")
        state["visited_agents"] = ["general"]
        state["supervisor_decision"] = {
            "route": "general",
            "reason": "general_conversation",
            "confidence": 0.9,
        }

        self.assertEqual(
            SupervisorRouter.route(state),
            SupervisorDestination.FAILURE,
        )

    def test_email_cannot_be_selected_after_email_handoff(self):
        state = build_initial_multi_agent_state("Send an email")
        state["visited_agents"] = ["email"]
        state["supervisor_decision"] = {
            "route": "email",
            "reason": "action_required",
            "confidence": 0.9,
        }

        self.assertEqual(
            SupervisorRouter.route(state),
            SupervisorDestination.FAILURE,
        )

    def test_invalid_visited_agents_routes_to_failure(self):
        state = build_initial_multi_agent_state("Hello")
        state["visited_agents"] = ["unknown"]
        state["supervisor_decision"] = {
            "route": "general",
            "reason": "general_conversation",
            "confidence": 0.9,
        }

        self.assertEqual(
            SupervisorRouter.route(state),
            SupervisorDestination.FAILURE,
        )

    def test_failed_or_invalid_task_status_routes_to_failure(self):
        for status in (TaskStatus.FAILED, "unknown"):
            with self.subTest(status=status):
                state = build_initial_multi_agent_state("Request")
                state["task_status"] = status
                state["supervisor_decision"] = {
                    "route": "general",
                    "reason": "general_conversation",
                    "confidence": 1.0,
                }

                self.assertEqual(
                    SupervisorRouter.route(state),
                    SupervisorDestination.FAILURE,
                )


if __name__ == "__main__":
    unittest.main()
