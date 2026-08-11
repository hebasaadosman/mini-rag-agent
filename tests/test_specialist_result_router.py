import unittest

from agents.multi_agent.specialist_result_router import (
    SpecialistResultDestination,
    SpecialistResultRouter,
)
from agents.multi_agent.state import AgentName, TaskStatus


def _state(
    status,
    *,
    agent=AgentName.GENERAL,
    final_response=None,
    resume_target=None,
    pending_interrupt=None,
    handoff_reason=None,
    error=None,
):
    return {
        "task_status": status,
        "active_agent": agent,
        "resume_target": resume_target,
        "pending_interrupt": pending_interrupt,
        "handoff_reason": handoff_reason,
        "supervisor_decision": None,
        "final_response": final_response,
        "error": error,
    }


class SpecialistResultRouterTests(unittest.TestCase):
    def test_completed_and_cancelled_results_end(self):
        for status in (TaskStatus.COMPLETED, TaskStatus.CANCELLED):
            with self.subTest(status=status):
                destination = SpecialistResultRouter.route(
                    _state(status, final_response={"success": True}),
                    expected_agent=AgentName.GENERAL,
                )
                self.assertEqual(
                    destination,
                    SpecialistResultDestination.END,
                )

    def test_waiting_result_ends_with_resumable_checkpoint(self):
        destination = SpecialistResultRouter.route(
            _state(
                TaskStatus.WAITING_FOR_USER,
                agent=AgentName.UTILITY,
                resume_target=AgentName.UTILITY,
                pending_interrupt={"type": "clarification"},
                final_response={"status": "clarification_required"},
            ),
            expected_agent=AgentName.UTILITY,
        )

        self.assertEqual(destination, SpecialistResultDestination.END)

    def test_handoff_returns_to_supervisor(self):
        destination = SpecialistResultRouter.route(
            _state(
                TaskStatus.RUNNING,
                handoff_reason="external_information",
            ),
            expected_agent=AgentName.GENERAL,
        )

        self.assertEqual(
            destination,
            SpecialistResultDestination.SUPERVISOR,
        )

    def test_failure_and_error_reach_failure_node(self):
        invalid_states = [
            _state(TaskStatus.FAILED),
            _state(TaskStatus.COMPLETED, error="failed"),
        ]

        for state in invalid_states:
            with self.subTest(state=state):
                self.assertEqual(
                    SpecialistResultRouter.route(
                        state,
                        expected_agent=AgentName.GENERAL,
                    ),
                    SpecialistResultDestination.FAILURE,
                )

    def test_corrupted_specialist_results_fail_safely(self):
        invalid_states = [
            _state(
                TaskStatus.COMPLETED,
                agent=AgentName.EMAIL,
                final_response={"success": True},
            ),
            _state(TaskStatus.RUNNING, handoff_reason=None),
            _state(
                TaskStatus.WAITING_FOR_USER,
                resume_target=AgentName.GENERAL,
                pending_interrupt=None,
                final_response={"success": True},
            ),
            _state(TaskStatus.COMPLETED, final_response=None),
        ]

        for state in invalid_states:
            with self.subTest(state=state):
                self.assertEqual(
                    SpecialistResultRouter.route(
                        state,
                        expected_agent=AgentName.GENERAL,
                    ),
                    SpecialistResultDestination.FAILURE,
                )


if __name__ == "__main__":
    unittest.main()
