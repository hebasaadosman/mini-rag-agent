import unittest

from agents.multi_agent import AgentName, TaskStatus
from agents.multi_agent.nodes import SupervisorClarificationNode


class SupervisorClarificationNodeTests(unittest.IsolatedAsyncioTestCase):
    async def test_builds_a_resumable_supervisor_clarification(self):
        node = SupervisorClarificationNode(
            interrupt_id_factory=lambda: "supervisor-interrupt-1"
        )
        state = {
            "supervisor_decision": {
                "route": "clarification",
                "reason": "ambiguous_request",
                "confidence": 0.4,
                "clarification_question": "Which service do you need?",
            }
        }

        update = await node(state)

        self.assertEqual(update["active_agent"], AgentName.SUPERVISOR)
        self.assertEqual(update["resume_target"], AgentName.SUPERVISOR)
        self.assertEqual(
            update["task_status"],
            TaskStatus.WAITING_FOR_USER,
        )
        self.assertEqual(
            update["pending_interrupt"]["type"],
            "routing_clarification",
        )
        self.assertEqual(
            update["final_response"]["status"],
            "clarification_required",
        )
        self.assertEqual(
            update["final_response"]["interrupt_id"],
            "supervisor-interrupt-1",
        )

    async def test_rejects_a_non_clarification_decision(self):
        update = await SupervisorClarificationNode()(
            {
                "supervisor_decision": {
                    "route": "general",
                    "reason": "general_conversation",
                    "confidence": 0.9,
                }
            }
        )

        self.assertEqual(update["task_status"], TaskStatus.FAILED)
        self.assertEqual(update["final_response"]["status"], "failed")

    async def test_rejects_an_invalid_supervisor_decision(self):
        update = await SupervisorClarificationNode()(
            {"supervisor_decision": {"route": "clarification"}}
        )

        self.assertEqual(update["task_status"], TaskStatus.FAILED)


if __name__ == "__main__":
    unittest.main()
