import unittest

from langgraph.graph import END, START, StateGraph

from agents.multi_agent.graph import MultiAgentGraph
from agents.multi_agent.state import (
    AgentName,
    TaskStatus,
    build_initial_multi_agent_state,
)


class _FakeSupervisor:
    _REASONS = {
        "knowledge": "project_knowledge",
        "utility": "external_information",
        "general": "general_conversation",
        "email": "action_required",
        "clarification": "ambiguous_request",
    }

    def __init__(self, route="general"):
        self.calls = 0
        self.resume_calls = 0
        self.routes = list(route) if isinstance(route, (list, tuple)) else [route]

    async def __call__(self, state):
        self.calls += 1
        return self._decision()

    async def resume(self, state):
        self.resume_calls += 1
        return self._decision()

    def _decision(self):
        decision_index = min(
            self.calls + self.resume_calls - 1,
            len(self.routes) - 1,
        )
        route = self.routes[decision_index]
        decision = {
            "route": route,
            "reason": self._REASONS[route],
            "confidence": 0.9,
        }
        if route == "clarification":
            decision["clarification_question"] = "Which service?"
        return {
            "supervisor_decision": decision,
            "active_agent": AgentName.SUPERVISOR.value,
            "task_status": TaskStatus.RUNNING.value,
            "error": None,
        }


class _FakeSpecialist:
    def __init__(self, name="specialist", mode="completed"):
        self.calls = 0
        self.resume_calls = 0
        self.name = name
        self.mode = mode

    async def __call__(self, state):
        self.calls += 1
        return self._update(self.name)

    async def resume(self, state):
        self.resume_calls += 1
        return self._update(f"resumed_{self.name}")

    def _update(self, response_agent):
        if self.mode == "waiting":
            return {
                "active_agent": AgentName(self.name).value,
                "resume_target": AgentName(self.name).value,
                "task_status": TaskStatus.WAITING_FOR_USER.value,
                "pending_interrupt": {
                    "type": "clarification",
                    "question": "Which option?",
                },
                "final_response": {
                    "status": "clarification_required",
                    "agent": response_agent,
                },
                "error": None,
            }
        if self.mode == "handoff":
            return {
                "supervisor_decision": None,
                "active_agent": AgentName(self.name).value,
                "resume_target": None,
                "task_status": TaskStatus.RUNNING.value,
                "pending_interrupt": None,
                "handoff_count": 1,
                "handoff_reason": "external_information",
                "visited_agents": [AgentName(self.name).value],
                "final_response": None,
                "error": None,
            }
        if self.mode == "failed":
            return {
                "active_agent": AgentName(self.name).value,
                "task_status": TaskStatus.FAILED.value,
                "final_response": None,
                "error": "The specialist failed safely.",
            }
        return self._completed_update(response_agent)

    def _completed_update(self, response_agent):
        return {
            "active_agent": AgentName(self.name).value,
            "resume_target": None,
            "task_status": TaskStatus.COMPLETED.value,
            "pending_interrupt": None,
            "final_response": {"agent": response_agent},
            "error": None,
        }


class _NonResumableAgent:
    async def __call__(self, state):
        return {}


def _dependencies(supervisor_route="general"):
    return {
        "supervisor": _FakeSupervisor(supervisor_route),
        "knowledge_agent": _FakeSpecialist("knowledge"),
        "utility_agent": _FakeSpecialist("utility"),
        "general_agent": _FakeSpecialist("general"),
        "email_agent": _FakeSpecialist("email"),
    }


class MultiAgentGraphTests(unittest.TestCase):
    def test_accepts_callable_agents_with_resumable_specialists(self):
        graph = MultiAgentGraph(**_dependencies())

        self.assertIsInstance(graph._create_builder(), StateGraph)
        self.assertIsNotNone(graph.compiled_graph)

    def test_starts_with_the_conversation_gate_node(self):
        graph = MultiAgentGraph(**_dependencies())

        self.assertIn("conversation_gate", graph._builder.nodes)
        self.assertIn(
            (START, "conversation_gate"),
            graph._builder.edges,
        )

    def test_registers_new_and_resume_execution_nodes(self):
        graph = MultiAgentGraph(**_dependencies())
        expected_nodes = {
            "conversation_gate",
            "supervisor",
            "resume_supervisor",
            "supervisor_clarification",
            "knowledge",
            "utility",
            "general",
            "email",
            "resume_knowledge",
            "resume_utility",
            "resume_general",
            "resume_email",
            "request_switch_confirmation",
            "continue_current_task",
            "switch_to_new_request",
            "rejection",
            "failure",
        }

        self.assertEqual(set(graph._builder.nodes), expected_nodes)
        self.assertEqual(
            graph._builder.edges,
            {
                (START, "conversation_gate"),
                ("supervisor_clarification", END),
                ("request_switch_confirmation", END),
                ("continue_current_task", END),
                ("switch_to_new_request", "supervisor"),
                ("rejection", END),
                ("failure", END),
            },
        )

    def test_rejects_a_non_callable_supervisor(self):
        dependencies = _dependencies()
        dependencies["supervisor"] = object()

        with self.assertRaisesRegex(TypeError, "supervisor must be callable"):
            MultiAgentGraph(**dependencies)

    def test_rejects_a_specialist_without_resume(self):
        dependencies = _dependencies()
        dependencies["email_agent"] = _NonResumableAgent()

        with self.assertRaisesRegex(TypeError, "async resume method"):
            MultiAgentGraph(**dependencies)


class MultiAgentGraphRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_new_message_reaches_supervisor_then_selected_specialist(self):
        dependencies = _dependencies()
        graph = MultiAgentGraph(**dependencies).compiled_graph

        result = await graph.ainvoke(
            build_initial_multi_agent_state("Hello")
        )

        self.assertEqual(dependencies["supervisor"].calls, 1)
        self.assertEqual(dependencies["general_agent"].calls, 1)
        self.assertEqual(result["final_response"]["agent"], "general")

    async def test_waiting_specialist_pauses_with_its_checkpoint(self):
        dependencies = _dependencies("utility")
        dependencies["utility_agent"] = _FakeSpecialist(
            "utility",
            mode="waiting",
        )
        graph = MultiAgentGraph(**dependencies).compiled_graph

        result = await graph.ainvoke(
            build_initial_multi_agent_state("What is the weather?")
        )

        self.assertEqual(result["task_status"], TaskStatus.WAITING_FOR_USER)
        self.assertEqual(result["resume_target"], AgentName.UTILITY)
        self.assertEqual(
            result["final_response"]["status"],
            "clarification_required",
        )

    async def test_failed_specialist_reaches_the_safe_failure_node(self):
        dependencies = _dependencies("general")
        dependencies["general_agent"] = _FakeSpecialist(
            "general",
            mode="failed",
        )
        graph = MultiAgentGraph(**dependencies).compiled_graph

        result = await graph.ainvoke(
            build_initial_multi_agent_state("Hello")
        )

        self.assertEqual(result["task_status"], TaskStatus.FAILED)
        self.assertEqual(result["final_response"]["status"], "failed")
        self.assertEqual(
            result["final_response"]["error"],
            "The specialist failed safely.",
        )

    async def test_specialist_handoff_returns_to_supervisor_then_new_agent(self):
        dependencies = _dependencies(["general", "utility"])
        dependencies["general_agent"] = _FakeSpecialist(
            "general",
            mode="handoff",
        )
        graph = MultiAgentGraph(**dependencies).compiled_graph

        result = await graph.ainvoke(
            build_initial_multi_agent_state("Tell me the weather")
        )

        self.assertEqual(dependencies["supervisor"].calls, 2)
        self.assertEqual(dependencies["general_agent"].calls, 1)
        self.assertEqual(dependencies["utility_agent"].calls, 1)
        self.assertEqual(result["final_response"]["agent"], "utility")
        self.assertEqual(result["visited_agents"], [AgentName.GENERAL])

    async def test_resume_reaches_only_the_saved_specialist_resume(self):
        dependencies = _dependencies()
        graph = MultiAgentGraph(**dependencies).compiled_graph
        state = self._waiting_state(AgentName.EMAIL)
        state["conversation_event"] = "resume"

        result = await graph.ainvoke(state)

        email_agent = dependencies["email_agent"]
        self.assertEqual(email_agent.calls, 0)
        self.assertEqual(email_agent.resume_calls, 1)
        self.assertEqual(
            result["final_response"]["agent"],
            "resumed_email",
        )
        self.assertEqual(dependencies["supervisor"].calls, 0)

    async def test_supervisor_clarification_resumes_the_supervisor(self):
        dependencies = _dependencies()
        graph = MultiAgentGraph(**dependencies).compiled_graph
        state = self._waiting_state(AgentName.SUPERVISOR)
        state["pending_interrupt"]["type"] = "routing_clarification"
        state["conversation_event"] = "resume"

        result = await graph.ainvoke(state)

        supervisor = dependencies["supervisor"]
        self.assertEqual(supervisor.calls, 0)
        self.assertEqual(supervisor.resume_calls, 1)
        self.assertEqual(dependencies["general_agent"].calls, 1)
        self.assertEqual(
            result["final_response"]["agent"],
            "general",
        )

    async def test_supervisor_can_route_to_every_specialist(self):
        specialist_dependencies = {
            "knowledge": "knowledge_agent",
            "utility": "utility_agent",
            "general": "general_agent",
            "email": "email_agent",
        }

        for route, dependency_name in specialist_dependencies.items():
            with self.subTest(route=route):
                dependencies = _dependencies(route)
                graph = MultiAgentGraph(**dependencies).compiled_graph

                result = await graph.ainvoke(
                    build_initial_multi_agent_state("Route this")
                )

                self.assertEqual(dependencies[dependency_name].calls, 1)
                self.assertEqual(result["final_response"]["agent"], route)

    async def test_supervisor_clarification_pauses_before_a_specialist(self):
        dependencies = _dependencies("clarification")
        graph = MultiAgentGraph(**dependencies).compiled_graph

        result = await graph.ainvoke(
            build_initial_multi_agent_state("Do it")
        )

        self.assertEqual(
            result["final_response"]["status"],
            "clarification_required",
        )
        self.assertEqual(result["resume_target"], AgentName.SUPERVISOR)
        self.assertTrue(
            all(
                dependencies[name].calls == 0
                for name in (
                    "knowledge_agent",
                    "utility_agent",
                    "general_agent",
                    "email_agent",
                )
            )
        )

    async def test_invalid_resume_reaches_the_rejection_node(self):
        graph = MultiAgentGraph(**_dependencies()).compiled_graph
        state = build_initial_multi_agent_state("Continue")
        state["conversation_event"] = "resume"

        result = await graph.ainvoke(state)

        self.assertEqual(result["final_response"]["status"], "rejected")

    async def test_corrupted_checkpoint_reaches_the_failure_node(self):
        graph = MultiAgentGraph(**_dependencies()).compiled_graph
        state = self._waiting_state(AgentName.KNOWLEDGE)
        state["conversation_event"] = "resume"
        state["pending_interrupt"] = None

        result = await graph.ainvoke(state)

        self.assertEqual(result["task_status"], TaskStatus.FAILED)
        self.assertEqual(result["final_response"]["status"], "failed")

    async def test_new_message_while_waiting_requests_switch_confirmation(self):
        graph = MultiAgentGraph(**_dependencies()).compiled_graph
        state = self._waiting_state(AgentName.UTILITY)

        result = await graph.ainvoke(state)

        self.assertEqual(
            result["final_response"]["status"],
            "switch_confirmation_required",
        )
        self.assertEqual(result["resume_target"], AgentName.UTILITY)
        self.assertIsNotNone(result["pending_interrupt"])

    @staticmethod
    def _waiting_state(target: AgentName):
        state = build_initial_multi_agent_state("New request")
        state["task_status"] = TaskStatus.WAITING_FOR_USER
        state["active_agent"] = target
        state["resume_target"] = target
        state["pending_interrupt"] = {
            "type": "clarification",
            "question": "Which option?",
        }
        return state

if __name__ == "__main__":
    unittest.main()
