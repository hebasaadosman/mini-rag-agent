import unittest

from agents.multi_agent import (
    AgentName,
    ConversationEvent,
    ConversationGate,
    ConversationGateEventError,
    ConversationGateStateError,
    ConversationRoute,
    TaskStatus,
    build_initial_multi_agent_state,
)


class ConversationGateTests(unittest.TestCase):
    def test_new_message_routes_to_supervisor_when_no_task_is_pending(self):
        state = build_initial_multi_agent_state("Hello")

        decision = ConversationGate.decide(
            state,
            ConversationEvent.NEW_MESSAGE,
        )

        self.assertEqual(decision.route, ConversationRoute.SUPERVISOR)
        self.assertIsNone(decision.target)

    def test_resume_routes_directly_to_the_saved_agent(self):
        state = self._build_waiting_state(AgentName.KNOWLEDGE)

        decision = ConversationGate.decide(
            state,
            ConversationEvent.RESUME,
        )

        self.assertEqual(decision.route, ConversationRoute.RESUME_TARGET)
        self.assertEqual(decision.target, AgentName.KNOWLEDGE)

    def test_checkpoint_string_values_are_normalized(self):
        state = self._build_waiting_state(AgentName.KNOWLEDGE)
        state["task_status"] = TaskStatus.WAITING_FOR_USER.value
        state["resume_target"] = AgentName.KNOWLEDGE.value

        decision = ConversationGate.decide(
            state,
            ConversationEvent.RESUME.value,
        )

        self.assertEqual(decision.route, ConversationRoute.RESUME_TARGET)
        self.assertEqual(decision.target, AgentName.KNOWLEDGE)

    def test_new_message_requires_switch_confirmation_while_waiting(self):
        state = self._build_waiting_state(AgentName.UTILITY)

        decision = ConversationGate.decide(
            state,
            ConversationEvent.NEW_MESSAGE,
        )

        self.assertEqual(
            decision.route,
            ConversationRoute.REQUEST_SWITCH_CONFIRMATION,
        )
        self.assertIsNone(decision.target)

    def test_switch_confirmation_can_continue_the_pending_task(self):
        state = self._build_waiting_state(AgentName.UTILITY)
        state["switch_confirmation_pending"] = True
        state["pending_switch_message"] = "Say hello instead"
        state["pending_user_message"] = "continue_current_task"

        decision = ConversationGate.decide(
            state,
            ConversationEvent.RESUME,
        )

        self.assertEqual(
            decision.route,
            ConversationRoute.CONTINUE_CURRENT_TASK,
        )

    def test_switch_confirmation_can_select_the_new_request(self):
        state = self._build_waiting_state(AgentName.UTILITY)
        state["switch_confirmation_pending"] = True
        state["pending_switch_message"] = "Say hello instead"
        state["pending_user_message"] = "switch_to_new_request"

        decision = ConversationGate.decide(
            state,
            ConversationEvent.RESUME,
        )

        self.assertEqual(
            decision.route,
            ConversationRoute.SWITCH_TO_NEW_REQUEST,
        )

    def test_invalid_switch_decision_requests_confirmation_again(self):
        state = self._build_waiting_state(AgentName.UTILITY)
        state["switch_confirmation_pending"] = True
        state["pending_switch_message"] = "Say hello instead"
        state["pending_user_message"] = "maybe"

        decision = ConversationGate.decide(
            state,
            ConversationEvent.RESUME,
        )

        self.assertEqual(
            decision.route,
            ConversationRoute.REQUEST_SWITCH_CONFIRMATION,
        )

    def test_resume_is_rejected_when_no_task_is_pending(self):
        state = build_initial_multi_agent_state("Continue")

        decision = ConversationGate.decide(
            state,
            ConversationEvent.RESUME,
        )

        self.assertEqual(decision.route, ConversationRoute.REJECT)
        self.assertIsNotNone(decision.reason)

    def test_new_message_is_rejected_while_an_agent_is_running(self):
        state = build_initial_multi_agent_state("Another request")
        state["active_agent"] = AgentName.KNOWLEDGE

        decision = ConversationGate.decide(
            state,
            ConversationEvent.NEW_MESSAGE,
        )

        self.assertEqual(decision.route, ConversationRoute.REJECT)

    def test_unsupported_event_is_rejected(self):
        state = build_initial_multi_agent_state("Hello")

        with self.assertRaises(ConversationGateEventError):
            ConversationGate.decide(state, "unknown")

    def test_invalid_checkpoint_status_is_rejected(self):
        state = build_initial_multi_agent_state("Hello")
        state["task_status"] = "unknown"

        with self.assertRaises(ConversationGateStateError):
            ConversationGate.decide(
                state,
                ConversationEvent.NEW_MESSAGE,
            )

    def test_waiting_state_requires_an_interrupt(self):
        state = self._build_waiting_state(AgentName.KNOWLEDGE)
        state["pending_interrupt"] = None

        with self.assertRaises(ConversationGateStateError):
            ConversationGate.decide(state, ConversationEvent.RESUME)

    def test_waiting_state_requires_a_resume_target(self):
        state = self._build_waiting_state(AgentName.KNOWLEDGE)
        state["resume_target"] = None

        with self.assertRaises(ConversationGateStateError):
            ConversationGate.decide(state, ConversationEvent.RESUME)

    def test_waiting_state_rejects_an_unknown_resume_target(self):
        state = self._build_waiting_state(AgentName.KNOWLEDGE)
        state["resume_target"] = "unknown"

        with self.assertRaises(ConversationGateStateError):
            ConversationGate.decide(state, ConversationEvent.RESUME)

    @staticmethod
    def _build_waiting_state(target: AgentName):
        state = build_initial_multi_agent_state("Pending question")
        state["task_status"] = TaskStatus.WAITING_FOR_USER
        state["pending_interrupt"] = {
            "type": "clarification",
            "question": "Which report?",
        }
        state["resume_target"] = target
        return state


if __name__ == "__main__":
    unittest.main()
