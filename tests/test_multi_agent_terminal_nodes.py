import unittest

from agents.multi_agent import AgentName, TaskStatus
from agents.multi_agent.nodes import (
    ContinueCurrentTaskNode,
    FailureNode,
    GateRejectionNode,
    GateSwitchConfirmationNode,
    SwitchToNewRequestNode,
)


class _CancellableSpecialist:
    def __init__(self, error=None):
        self.error = error
        self.calls = []

    async def cancel_pending(self, state):
        self.calls.append(state)
        if self.error is not None:
            raise self.error


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

    async def test_continue_current_task_restores_clarification(self):
        update = await ContinueCurrentTaskNode()(
            {
                "resume_target": "utility",
                "pending_interrupt": {
                    "type": "clarification",
                    "question": "Which city?",
                    "options": [],
                    "interrupt_id": "utility-1",
                },
            }
        )

        self.assertEqual(
            update["final_response"]["status"],
            "clarification_required",
        )
        self.assertFalse(update["switch_confirmation_pending"])

    async def test_switch_to_new_request_resets_the_pending_task(self):
        specialist = _CancellableSpecialist()
        state = {
            "pending_switch_message": "Say hello",
            "resume_target": AgentName.KNOWLEDGE,
        }
        update = await SwitchToNewRequestNode(
            specialists={AgentName.KNOWLEDGE: specialist}
        )(state)

        self.assertEqual(update["user_message"], "Say hello")
        self.assertEqual(update["task_status"], TaskStatus.RUNNING)
        self.assertIsNone(update["pending_interrupt"])
        self.assertEqual(specialist.calls, [state])

    async def test_switch_fails_safely_when_pending_cleanup_fails(self):
        specialist = _CancellableSpecialist(RuntimeError("private"))

        update = await SwitchToNewRequestNode(
            specialists={AgentName.KNOWLEDGE: specialist}
        )(
            {
                "pending_switch_message": "Say hello",
                "resume_target": AgentName.KNOWLEDGE,
            }
        )

        self.assertEqual(update["task_status"], TaskStatus.FAILED)
        self.assertEqual(
            update["error"],
            "Failed to cancel the pending task safely.",
        )

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
