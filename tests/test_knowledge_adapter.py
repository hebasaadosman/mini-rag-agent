import unittest

from agents.multi_agent import (
    AgentName,
    ConversationEvent,
    ConversationGate,
    ConversationRoute,
    KnowledgeSpecialistAdapter,
    TaskStatus,
    build_initial_multi_agent_state,
)


class _FakeKnowledgeAgent:
    def __init__(
        self,
        *,
        run_result=None,
        resume_result=None,
        run_error=None,
        resume_error=None,
    ):
        self.run_result = run_result
        self.resume_result = resume_result
        self.run_error = run_error
        self.resume_error = resume_error
        self.run_calls = []
        self.resume_calls = []

    async def run(self, **kwargs):
        self.run_calls.append(kwargs)
        if self.run_error is not None:
            raise self.run_error
        return self.run_result

    async def resume(self, **kwargs):
        self.resume_calls.append(kwargs)
        if self.resume_error is not None:
            raise self.resume_error
        return self.resume_result


class _Factory:
    def __init__(self, agent):
        self.agent = agent
        self.project_ids = []

    def __call__(self, project_id):
        self.project_ids.append(project_id)
        return self.agent


def _state(message="Summarize the report"):
    return build_initial_multi_agent_state(
        message,
        project_id=7,
        thread_id="knowledge-thread-1",
    )


class KnowledgeSpecialistAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_clarification_resume_bypasses_supervisor(self):
        core = _FakeKnowledgeAgent(
            run_result={
                "success": True,
                "status": "clarification_required",
                "clarification": {
                    "type": "clarification",
                    "question": "Which report?",
                    "options": ["Sales", "Finance"],
                },
                "interrupt_id": "interrupt-1",
            },
            resume_result={
                "success": True,
                "status": "completed",
                "answer": "Sales report summary.",
            },
        )
        adapter = KnowledgeSpecialistAdapter(
            agent_factory=_Factory(core)
        )
        state = _state()

        state.update(await adapter.run(state))
        gate_decision = ConversationGate.decide(
            state,
            ConversationEvent.RESUME,
        )

        self.assertEqual(
            gate_decision.route,
            ConversationRoute.RESUME_TARGET,
        )
        self.assertEqual(gate_decision.target, AgentName.KNOWLEDGE)

        state["pending_user_message"] = "Sales"
        state.update(await adapter.resume(state))

        self.assertEqual(state["task_status"], TaskStatus.COMPLETED)
        self.assertEqual(state["final_response"]["agent"], "knowledge")

    async def test_completed_result_is_mapped_to_multi_agent_state(self):
        core = _FakeKnowledgeAgent(
            run_result={
                "success": True,
                "status": "completed",
                "answer": "The policy allows two remote days.",
                "iterations": 2,
                "used_chunk_ids": [11, "11", 0, "bad"],
                "memory_message_count": 4,
                "messages": [{"role": "SYSTEM", "content": "private"}],
                "tool_history": [{"tool_name": "private-tool"}],
            }
        )
        factory = _Factory(core)
        adapter = KnowledgeSpecialistAdapter(
            agent_factory=factory,
            system_prompt="KNOWLEDGE SYSTEM",
        )

        update = await adapter.run(_state())

        self.assertEqual(factory.project_ids, [7])
        self.assertEqual(
            core.run_calls,
            [
                {
                    "thread_id": "knowledge-thread-1",
                    "project_id": 7,
                    "user_message": "Summarize the report",
                    "system_prompt": "KNOWLEDGE SYSTEM",
                }
            ],
        )
        self.assertEqual(update["active_agent"], AgentName.KNOWLEDGE)
        self.assertEqual(update["task_status"], TaskStatus.COMPLETED)
        self.assertIsNone(update["resume_target"])
        self.assertEqual(update["final_response"]["agent"], "knowledge")
        self.assertEqual(update["final_response"]["used_chunk_ids"], [11])
        self.assertEqual(update["final_response"]["memory_message_count"], 4)
        self.assertEqual(
            update["messages"],
            [
                {"role": "user", "content": "Summarize the report"},
                {
                    "role": "assistant",
                    "content": "The policy allows two remote days.",
                },
            ],
        )

    async def test_clarification_result_saves_resume_target(self):
        core = _FakeKnowledgeAgent(
            run_result={
                "success": True,
                "status": "clarification_required",
                "answer": None,
                "clarification": {
                    "type": "clarification",
                    "question": "Which report?",
                    "options": ["Sales", "Finance"],
                },
                "interrupt_id": "interrupt-123",
                "iterations": 1,
            }
        )
        adapter = KnowledgeSpecialistAdapter(
            agent_factory=_Factory(core)
        )

        update = await adapter(_state())

        self.assertEqual(
            update["task_status"],
            TaskStatus.WAITING_FOR_USER,
        )
        self.assertEqual(update["resume_target"], AgentName.KNOWLEDGE)
        self.assertEqual(
            update["pending_interrupt"],
            {
                "type": "clarification",
                "question": "Which report?",
                "options": ["Sales", "Finance"],
                "interrupt_id": "interrupt-123",
            },
        )

    async def test_resume_calls_core_directly_and_clears_pending_state(self):
        core = _FakeKnowledgeAgent(
            resume_result={
                "success": True,
                "status": "completed",
                "answer": "Sales report summary.",
                "iterations": 3,
                "used_chunk_ids": [],
            }
        )
        factory = _Factory(core)
        adapter = KnowledgeSpecialistAdapter(agent_factory=factory)
        state = _state()
        state.update(
            {
                "task_status": TaskStatus.WAITING_FOR_USER,
                "resume_target": AgentName.KNOWLEDGE,
                "pending_interrupt": {
                    "type": "clarification",
                    "question": "Which report?",
                },
                "pending_user_message": "Sales",
            }
        )

        update = await adapter.resume(state)

        self.assertEqual(core.run_calls, [])
        self.assertEqual(
            core.resume_calls,
            [
                {
                    "thread_id": "knowledge-thread-1",
                    "response": "Sales",
                }
            ],
        )
        self.assertEqual(update["task_status"], TaskStatus.COMPLETED)
        self.assertIsNone(update["pending_interrupt"])
        self.assertIsNone(update["pending_user_message"])
        self.assertIsNone(update["resume_target"])

    async def test_repeated_clarification_remains_with_knowledge(self):
        clarification = {
            "type": "clarification",
            "question": "Choose an exact option.",
            "options": ["Sales", "Finance"],
        }
        core = _FakeKnowledgeAgent(
            resume_result={
                "success": True,
                "status": "clarification_required",
                "clarification": clarification,
                "interrupt_id": "same-interrupt",
            }
        )
        adapter = KnowledgeSpecialistAdapter(
            agent_factory=_Factory(core)
        )
        state = _state()
        state.update(
            {
                "task_status": TaskStatus.WAITING_FOR_USER,
                "resume_target": AgentName.KNOWLEDGE,
                "pending_interrupt": clarification,
                "pending_user_message": "Unknown report",
            }
        )

        update = await adapter.resume(state)

        self.assertEqual(update["task_status"], TaskStatus.WAITING_FOR_USER)
        self.assertEqual(update["resume_target"], AgentName.KNOWLEDGE)
        self.assertEqual(
            update["pending_interrupt"]["interrupt_id"],
            "same-interrupt",
        )

    async def test_resume_requires_a_knowledge_pending_state(self):
        core = _FakeKnowledgeAgent(resume_result={})
        adapter = KnowledgeSpecialistAdapter(
            agent_factory=_Factory(core)
        )

        update = await adapter.resume(_state())

        self.assertEqual(update["task_status"], TaskStatus.FAILED)
        self.assertIn("no pending clarification", update["error"])
        self.assertEqual(core.resume_calls, [])

    async def test_resume_requires_an_explicit_pending_user_message(self):
        core = _FakeKnowledgeAgent(resume_result={})
        adapter = KnowledgeSpecialistAdapter(
            agent_factory=_Factory(core)
        )
        state = _state()
        state.update(
            {
                "task_status": TaskStatus.WAITING_FOR_USER,
                "resume_target": AgentName.KNOWLEDGE,
                "pending_interrupt": {"question": "Which report?"},
            }
        )

        update = await adapter.resume(state)

        self.assertEqual(update["task_status"], TaskStatus.FAILED)
        self.assertIn("pending_user_message", update["error"])
        self.assertEqual(core.resume_calls, [])

    async def test_core_failure_is_preserved(self):
        core = _FakeKnowledgeAgent(
            run_result={
                "success": False,
                "status": "failed",
                "error": "Project index is unavailable.",
            }
        )
        adapter = KnowledgeSpecialistAdapter(
            agent_factory=_Factory(core)
        )

        update = await adapter(_state())

        self.assertEqual(update["task_status"], TaskStatus.FAILED)
        self.assertEqual(update["error"], "Project index is unavailable.")
        self.assertIsNone(update["final_response"])

    async def test_unexpected_core_exception_has_a_safe_error(self):
        core = _FakeKnowledgeAgent(run_error=RuntimeError("secret detail"))
        adapter = KnowledgeSpecialistAdapter(
            agent_factory=_Factory(core)
        )

        update = await adapter(_state())

        self.assertEqual(
            update["error"],
            "Failed to run the Knowledge Agent.",
        )
        self.assertNotIn("secret detail", update["error"])

    async def test_invalid_core_contract_is_rejected(self):
        invalid_results = [
            None,
            [],
            {"success": True, "status": "unknown"},
            {"success": True, "status": "completed", "answer": " "},
            {
                "success": True,
                "status": "clarification_required",
                "clarification": {"question": "", "options": []},
            },
        ]

        for result in invalid_results:
            with self.subTest(result=result):
                adapter = KnowledgeSpecialistAdapter(
                    agent_factory=_Factory(
                        _FakeKnowledgeAgent(run_result=result)
                    )
                )
                update = await adapter(_state())
                self.assertEqual(update["task_status"], TaskStatus.FAILED)

    async def test_missing_request_context_is_rejected_before_factory(self):
        factory = _Factory(_FakeKnowledgeAgent(run_result={}))
        adapter = KnowledgeSpecialistAdapter(agent_factory=factory)

        update = await adapter(
            build_initial_multi_agent_state("Summarize the report")
        )

        self.assertEqual(update["task_status"], TaskStatus.FAILED)
        self.assertIn("project_id", update["error"])
        self.assertEqual(factory.project_ids, [])


if __name__ == "__main__":
    unittest.main()
