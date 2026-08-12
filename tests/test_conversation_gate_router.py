import unittest

from agents.multi_agent.conversation_gate_router import (
    ConversationGateDestination,
    ConversationGateRouter,
)
from agents.multi_agent.state import MultiAgentState


def _state(route, *, target=None, reason=None) -> MultiAgentState:
    return {
        "gate_decision": {
            "route": route,
            "target": target,
            "reason": reason,
        },
        "error": None,
    }


class ConversationGateRouterTests(unittest.TestCase):
    def test_new_message_routes_to_supervisor(self):
        destination = ConversationGateRouter.route(_state("supervisor"))

        self.assertEqual(
            destination,
            ConversationGateDestination.SUPERVISOR,
        )

    def test_each_specialist_has_a_resume_destination(self):
        expected_destinations = {
            "supervisor": ConversationGateDestination.RESUME_SUPERVISOR,
            "knowledge": ConversationGateDestination.RESUME_KNOWLEDGE,
            "utility": ConversationGateDestination.RESUME_UTILITY,
            "general": ConversationGateDestination.RESUME_GENERAL,
            "email": ConversationGateDestination.RESUME_EMAIL,
        }

        for target, expected in expected_destinations.items():
            with self.subTest(target=target):
                destination = ConversationGateRouter.route(
                    _state("resume_target", target=target)
                )
                self.assertEqual(destination, expected)

    def test_switch_confirmation_and_rejection_have_separate_routes(self):
        switch = ConversationGateRouter.route(
            _state(
                "request_switch_confirmation",
                reason="A task is waiting.",
            )
        )
        rejection = ConversationGateRouter.route(
            _state("reject", reason="No task is waiting.")
        )

        self.assertEqual(
            switch,
            ConversationGateDestination.REQUEST_SWITCH_CONFIRMATION,
        )
        self.assertEqual(
            rejection,
            ConversationGateDestination.REJECTION,
        )

    def test_switch_decisions_have_separate_destinations(self):
        continue_current = ConversationGateRouter.route(
            _state("continue_current_task", target="utility")
        )
        switch_new = ConversationGateRouter.route(
            _state("switch_to_new_request")
        )

        self.assertEqual(
            continue_current,
            ConversationGateDestination.CONTINUE_CURRENT_TASK,
        )
        self.assertEqual(
            switch_new,
            ConversationGateDestination.SWITCH_TO_NEW_REQUEST,
        )

    def test_existing_error_routes_to_failure(self):
        state = _state("supervisor")
        state["error"] = "failed"

        self.assertEqual(
            ConversationGateRouter.route(state),
            ConversationGateDestination.FAILURE,
        )

    def test_missing_or_unknown_decision_routes_to_failure(self):
        invalid_states = [
            {},
            {"gate_decision": None},
            {"gate_decision": {"route": "unknown"}},
        ]

        for state in invalid_states:
            with self.subTest(state=state):
                self.assertEqual(
                    ConversationGateRouter.route(state),
                    ConversationGateDestination.FAILURE,
                )

    def test_corrupted_target_or_reason_routes_to_failure(self):
        invalid_states = [
            _state("supervisor", target="email"),
            _state("resume_target", target="email", reason="unexpected"),
            _state("reject", reason=""),
            _state("request_switch_confirmation", target="knowledge"),
        ]

        for state in invalid_states:
            with self.subTest(state=state):
                self.assertEqual(
                    ConversationGateRouter.route(state),
                    ConversationGateDestination.FAILURE,
                )


if __name__ == "__main__":
    unittest.main()
