import unittest

from agents.multi_agent import AgentName, TaskStatus
from agents.multi_agent.nodes import (
    FailureNode,
    GateRejectionNode,
    GateSwitchConfirmationNode,
)


class MultiAgentTerminalNodeTests(unittest.IsolatedAsyncioTestCase):
    async def test_failure_node_returns_a_safe_public_response(self):
        update = await FailureNode()({"error": "Provider failed."})

        self.assertEqual(update["task_status"], TaskStatus.FAILED)
        self.assertIsNone(update["active_agent"])
        self.assertIsNone(update["resume_target"])
        self.assertEqual(
            update["final_response"],
            {
                "success": False,
                "status": "failed",
                "agent": None,
                "answer": None,
                "error": "Provider failed.",
            },
        )

    async def test_failure_node_uses_a_safe_default_error(self):
        update = await FailureNode()({})

        self.assertEqual(
            update["error"],
            "The multi-agent workflow failed.",
        )

    async def test_rejection_node_returns_the_gate_reason(self):
        state = {
            "gate_decision": {
                "route": "reject",
                "target": None,
                "reason": "No task is waiting for a response.",
            }
        }

        update = await GateRejectionNode()(state)

        self.assertFalse(update["final_response"]["success"])
        self.assertEqual(update["final_response"]["status"], "rejected")
        self.assertEqual(
            update["final_response"]["error"],
            "No task is waiting for a response.",
        )

    async def test_switch_confirmation_preserves_the_pending_task(self):
        pending_interrupt = {
            "type": "clarification",
            "question": "Which report?",
        }
        state = {
            "task_status": TaskStatus.WAITING_FOR_USER,
            "resume_target": AgentName.KNOWLEDGE,
            "pending_interrupt": pending_interrupt,
            "gate_decision": {
                "route": "request_switch_confirmation",
                "target": None,
                "reason": "A task is waiting for the user's response.",
            },
        }

        update = await GateSwitchConfirmationNode()(state)

        self.assertEqual(
            update["final_response"]["status"],
            "switch_confirmation_required",
        )
        self.assertEqual(update["final_response"]["agent"], "knowledge")
        self.assertNotIn("task_status", update)
        self.assertNotIn("resume_target", update)
        self.assertNotIn("pending_interrupt", update)
        self.assertIs(state["pending_interrupt"], pending_interrupt)

    async def test_invalid_terminal_decisions_fail_safely(self):
        invalid_rejection = await GateRejectionNode()(
            {"gate_decision": {"route": "supervisor"}}
        )
        invalid_switch = await GateSwitchConfirmationNode()(
            {
                "resume_target": "supervisor",
                "gate_decision": {
                    "route": "request_switch_confirmation",
                    "reason": "Waiting.",
                },
            }
        )
        missing_pending_task = await GateSwitchConfirmationNode()(
            {
                "resume_target": "knowledge",
                "gate_decision": {
                    "route": "request_switch_confirmation",
                    "target": None,
                    "reason": "Waiting.",
                },
            }
        )

        self.assertEqual(
            invalid_rejection["task_status"],
            TaskStatus.FAILED,
        )
        self.assertEqual(
            invalid_switch["task_status"],
            TaskStatus.FAILED,
        )
        self.assertEqual(
            missing_pending_task["task_status"],
            TaskStatus.FAILED,
        )


if __name__ == "__main__":
    unittest.main()
