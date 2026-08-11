import unittest

from agents.multi_agent import (
    AgentName,
    TaskStatus,
    build_initial_multi_agent_state,
)


class MultiAgentStateTests(unittest.TestCase):
    def test_agent_names_are_stable_strings(self):
        self.assertEqual(AgentName.SUPERVISOR.value, "supervisor")
        self.assertEqual(AgentName.KNOWLEDGE.value, "knowledge")
        self.assertEqual(AgentName.UTILITY.value, "utility")
        self.assertEqual(AgentName.GENERAL.value, "general")
        self.assertEqual(AgentName.EMAIL.value, "email")

    def test_initial_state_has_safe_defaults(self):
        state = build_initial_multi_agent_state(
            "  What is the weather in Riyadh?  "
        )

        self.assertEqual(
            state["user_message"],
            "What is the weather in Riyadh?",
        )
        self.assertEqual(state["task_status"], TaskStatus.RUNNING)
        self.assertIsNone(state["active_agent"])
        self.assertIsNone(state["resume_target"])
        self.assertIsNone(state["pending_interrupt"])
        self.assertEqual(state["handoff_count"], 0)
        self.assertIsNone(state["handoff_reason"])
        self.assertEqual(state["visited_agents"], [])
        self.assertEqual(state["tool_history"], [])
        self.assertIsNone(state["final_response"])
        self.assertIsNone(state["error"])

    def test_initial_states_do_not_share_mutable_lists(self):
        first = build_initial_multi_agent_state("First request")
        second = build_initial_multi_agent_state("Second request")

        first["visited_agents"].append(AgentName.KNOWLEDGE)
        first["messages"].append({"role": "user"})

        self.assertEqual(second["visited_agents"], [])
        self.assertEqual(second["messages"], [])

    def test_blank_user_message_is_rejected(self):
        with self.assertRaises(ValueError):
            build_initial_multi_agent_state("   ")


if __name__ == "__main__":
    unittest.main()
