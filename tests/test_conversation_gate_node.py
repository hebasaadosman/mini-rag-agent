import unittest

from agents.multi_agent import (
    AgentName,
    TaskStatus,
    build_initial_multi_agent_state,
)
from agents.multi_agent.nodes import ConversationGateNode


class ConversationGateNodeTests(unittest.IsolatedAsyncioTestCase):
    async def test_new_message_records_the_supervisor_route(self):
        state = build_initial_multi_agent_state("Hello")

        update = await ConversationGateNode()(state)

        self.assertEqual(update["gate_decision"]["route"], "supervisor")
        self.assertIsNone(update["gate_decision"]["target"])
        self.assertIsNone(update["error"])

    async def test_resume_records_the_saved_specialist_target(self):
        state = self._waiting_state(AgentName.EMAIL)
        state["conversation_event"] = "resume"

        update = await ConversationGateNode()(state)

        self.assertEqual(update["gate_decision"]["route"], "resume_target")
        self.assertEqual(update["gate_decision"]["target"], "email")
        self.assertIsNone(update["error"])

    async def test_resume_without_pending_task_records_rejection(self):
        state = build_initial_multi_agent_state("Continue")
        state["conversation_event"] = "resume"

        update = await ConversationGateNode()(state)

        self.assertEqual(update["gate_decision"]["route"], "reject")
        self.assertIsNotNone(update["gate_decision"]["reason"])
        self.assertIsNone(update["error"])

    async def test_invalid_waiting_checkpoint_fails_safely(self):
        state = self._waiting_state(AgentName.KNOWLEDGE)
        state["conversation_event"] = "resume"
        state["pending_interrupt"] = None

        update = await ConversationGateNode()(state)

        self.assertIsNone(update["gate_decision"])
        self.assertEqual(update["task_status"], TaskStatus.FAILED)
        self.assertIsNone(update["active_agent"])
        self.assertIn("pending_interrupt", update["error"])

    @staticmethod
    def _waiting_state(target: AgentName):
        state = build_initial_multi_agent_state("Pending task")
        state["task_status"] = TaskStatus.WAITING_FOR_USER
        state["pending_interrupt"] = {
            "type": "clarification",
            "question": "Which report?",
        }
        state["resume_target"] = target
        return state


if __name__ == "__main__":
    unittest.main()
