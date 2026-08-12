import unittest

from langgraph.checkpoint.memory import InMemorySaver

from agents.multi_agent.graph import MultiAgentGraph
from agents.multi_agent.runtime import MultiAgentRuntime
from tests.test_multi_agent_graph import _FakeSpecialist, _dependencies


def _runtime(*, dependencies=None, checkpointer=True):
    dependencies = dependencies or _dependencies()
    graph = MultiAgentGraph(
        **dependencies,
        checkpointer=InMemorySaver() if checkpointer else None,
    )
    return MultiAgentRuntime(graph), graph, dependencies


class MultiAgentRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_chat_runs_the_public_workflow(self):
        runtime, _, dependencies = _runtime()

        result = await runtime.chat(
            thread_id="runtime-001",
            message="Hello",
        )

        self.assertEqual(result, {"agent": "general"})
        self.assertEqual(dependencies["supervisor"].calls, 1)
        self.assertEqual(dependencies["general_agent"].calls, 1)

    async def test_completed_thread_accepts_a_new_turn(self):
        runtime, _, dependencies = _runtime()

        await runtime.chat(thread_id="runtime-002", message="First")
        result = await runtime.chat(
            thread_id="runtime-002",
            message="Second",
        )

        self.assertEqual(result, {"agent": "general"})
        self.assertEqual(dependencies["supervisor"].calls, 2)
        self.assertEqual(dependencies["general_agent"].calls, 2)

    async def test_resume_uses_the_saved_specialist_checkpoint(self):
        dependencies = _dependencies("utility")
        utility = _FakeSpecialist("utility", mode="waiting")
        dependencies["utility_agent"] = utility
        runtime, _, _ = _runtime(dependencies=dependencies)

        waiting = await runtime.chat(
            thread_id="runtime-003",
            message="Weather",
        )
        utility.mode = "completed"
        completed = await runtime.resume(
            thread_id="runtime-003",
            response="Riyadh",
        )

        self.assertEqual(waiting["status"], "clarification_required")
        self.assertEqual(completed, {"agent": "resumed_utility"})
        self.assertEqual(utility.calls, 1)
        self.assertEqual(utility.resume_calls, 1)

    async def test_new_message_while_waiting_does_not_run_another_agent(self):
        dependencies = _dependencies("utility")
        utility = _FakeSpecialist("utility", mode="waiting")
        dependencies["utility_agent"] = utility
        runtime, _, _ = _runtime(dependencies=dependencies)

        await runtime.chat(
            thread_id="runtime-004",
            message="Weather",
        )
        result = await runtime.chat(
            thread_id="runtime-004",
            message="Send an email instead",
        )

        self.assertEqual(
            result["status"],
            "switch_confirmation_required",
        )
        self.assertEqual(utility.calls, 1)
        self.assertEqual(dependencies["email_agent"].calls, 0)

    async def test_continue_switch_decision_restores_the_old_prompt(self):
        dependencies = _dependencies("utility")
        utility = _FakeSpecialist("utility", mode="waiting")
        dependencies["utility_agent"] = utility
        runtime, _, _ = _runtime(dependencies=dependencies)

        await runtime.chat(
            thread_id="runtime-switch-continue",
            message="Weather",
        )
        await runtime.chat(
            thread_id="runtime-switch-continue",
            message="Say hello instead",
        )
        result = await runtime.resume(
            thread_id="runtime-switch-continue",
            response="continue_current_task",
        )

        self.assertEqual(result["status"], "clarification_required")
        self.assertEqual(result["agent"], "utility")
        self.assertEqual(utility.resume_calls, 0)
        self.assertEqual(dependencies["supervisor"].calls, 1)

    async def test_switch_decision_runs_the_saved_new_request(self):
        dependencies = _dependencies(("utility", "general"))
        utility = _FakeSpecialist("utility", mode="waiting")
        dependencies["utility_agent"] = utility
        runtime, _, _ = _runtime(dependencies=dependencies)

        await runtime.chat(
            thread_id="runtime-switch-new",
            message="Weather",
        )
        await runtime.chat(
            thread_id="runtime-switch-new",
            message="Say hello instead",
        )
        result = await runtime.resume(
            thread_id="runtime-switch-new",
            response="switch_to_new_request",
        )

        self.assertEqual(result, {"agent": "general"})
        self.assertEqual(dependencies["supervisor"].calls, 2)
        self.assertEqual(dependencies["general_agent"].calls, 1)
        self.assertEqual(utility.resume_calls, 0)

    async def test_supervisor_clarification_reopens_specialist_routing(self):
        dependencies = _dependencies(
            ("general", "clarification", "general")
        )
        general = _FakeSpecialist("general", mode="handoff")
        dependencies["general_agent"] = general
        runtime, _, _ = _runtime(dependencies=dependencies)

        waiting = await runtime.chat(
            thread_id="runtime-supervisor-retry",
            message="What is the capital of an unknown place?",
        )
        general.mode = "completed"
        completed = await runtime.resume(
            thread_id="runtime-supervisor-retry",
            response="Spain",
        )

        self.assertEqual(waiting["status"], "clarification_required")
        self.assertEqual(waiting["agent"], "supervisor")
        self.assertEqual(completed, {"agent": "general"})
        self.assertEqual(general.calls, 2)
        self.assertEqual(dependencies["supervisor"].calls, 2)
        self.assertEqual(dependencies["supervisor"].resume_calls, 1)

    async def test_resume_without_pending_task_is_rejected_safely(self):
        runtime, _, _ = _runtime()

        result = await runtime.resume(
            thread_id="runtime-missing",
            response="Continue",
        )

        self.assertEqual(result["status"], "rejected")

    async def test_thread_cannot_silently_change_projects(self):
        runtime, _, _ = _runtime()
        await runtime.chat(
            thread_id="runtime-project",
            message="First",
            project_id=1,
        )

        with self.assertRaisesRegex(ValueError, "different project"):
            await runtime.chat(
                thread_id="runtime-project",
                message="Second",
                project_id=2,
            )

    async def test_resume_cannot_silently_change_projects(self):
        runtime, _, _ = _runtime()
        await runtime.chat(
            thread_id="runtime-resume-project",
            message="First",
            project_id=1,
        )

        with self.assertRaisesRegex(ValueError, "different project"):
            await runtime.resume(
                thread_id="runtime-resume-project",
                response="Continue",
                project_id=2,
            )

    async def test_resume_requires_persistent_checkpointing(self):
        runtime, _, _ = _runtime(checkpointer=False)

        with self.assertRaisesRegex(RuntimeError, "checkpointer"):
            await runtime.resume(
                thread_id="runtime-no-memory",
                response="Continue",
            )

    async def test_validates_public_inputs(self):
        runtime, _, _ = _runtime()

        with self.assertRaisesRegex(ValueError, "thread_id"):
            await runtime.chat(thread_id=" ", message="Hello")
        with self.assertRaisesRegex(ValueError, "user_message"):
            await runtime.chat(thread_id="runtime", message=" ")
        with self.assertRaisesRegex(ValueError, "response"):
            await runtime.resume(thread_id="runtime", response=" ")


if __name__ == "__main__":
    unittest.main()
