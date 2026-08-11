import json
import unittest
from enum import Enum
from typing import Any

from agents.multi_agent import (
    AgentName,
    ConversationEvent,
    ConversationGate,
    ConversationRoute,
    TaskStatus,
    UtilityAgent,
    build_initial_multi_agent_state,
)
from agents.tools import BaseTool, ToolRegistry


class _Role(Enum):
    SYSTEM = "SYSTEM"
    USER = "USER"
    ASSISTANT = "CHATBOT"


class _FakeProvider:
    enums = _Role

    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []
        self.tool_results = []

    def construct_prompt(self, prompt, role):
        return {"role": role, "content": prompt}

    def generate_tool_response(self, **kwargs):
        self.calls.append(kwargs)
        return next(self.responses)

    def construct_assistant_tool_message(self, response):
        return {
            "role": "CHATBOT",
            "tool_calls": response["tool_calls"],
        }

    def construct_tool_result_message(
        self,
        *,
        tool_call_id,
        tool_name,
        result,
    ):
        record = {
            "role": "TOOL",
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
            "result": result,
        }
        self.tool_results.append(record)
        return record


class _FakeTool(BaseTool):
    description = "Fake utility tool"

    def __init__(self, name, result):
        self.name = name
        self.result = result
        self.calls = []

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "string"},
                    },
                    "required": ["location"],
                },
            },
        }

    async def execute(self, **kwargs):
        self.calls.append(kwargs)
        return self.result


def _registry_with(*tools):
    registry = ToolRegistry()
    for tool in tools:
        registry.register_tool(tool)
    return registry


class UtilityAgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_location_pauses_and_resumes_utility(self):
        provider = _FakeProvider(
            [
                {
                    "content": json.dumps(
                        {
                            "action": "clarification",
                            "question": "Which city?",
                            "options": [],
                        }
                    ),
                    "tool_calls": [],
                },
                {
                    "content": json.dumps(
                        {
                            "action": "answer",
                            "answer": "It is clear in Riyadh.",
                        }
                    ),
                    "tool_calls": [],
                },
            ]
        )
        agent = UtilityAgent(
            llm_provider=provider,
            tool_registry=ToolRegistry(),
            interrupt_id_factory=lambda: "utility-id-1",
        )
        state = build_initial_multi_agent_state("What is the weather?")

        state.update(await agent(state))

        self.assertEqual(state["task_status"], TaskStatus.WAITING_FOR_USER)
        self.assertEqual(state["resume_target"], AgentName.UTILITY)
        self.assertEqual(
            state["pending_interrupt"]["interrupt_id"],
            "utility-id-1",
        )
        decision = ConversationGate.decide(
            state,
            ConversationEvent.RESUME,
        )
        self.assertEqual(decision.route, ConversationRoute.RESUME_TARGET)
        self.assertEqual(decision.target, AgentName.UTILITY)

        state["pending_user_message"] = "Riyadh"
        state.update(await agent.resume(state))

        self.assertEqual(state["task_status"], TaskStatus.COMPLETED)
        self.assertIsNone(state["resume_target"])
        self.assertIsNone(state["pending_interrupt"])
        self.assertEqual(
            state["final_response"]["answer"],
            "It is clear in Riyadh.",
        )
        second_messages = provider.calls[1]["messages"]
        self.assertEqual(
            [message["role"] for message in second_messages],
            ["SYSTEM", "USER", "CHATBOT", "USER"],
        )

    async def test_resume_without_utility_interrupt_is_rejected(self):
        provider = _FakeProvider([])
        agent = UtilityAgent(
            llm_provider=provider,
            tool_registry=ToolRegistry(),
        )

        update = await agent.resume(
            build_initial_multi_agent_state("Weather?")
        )

        self.assertEqual(update["task_status"], TaskStatus.FAILED)
        self.assertEqual(provider.calls, [])

    async def test_executes_time_and_weather_tools_in_one_turn(self):
        time_tool = _FakeTool(
            "get_current_time",
            {"local_time": "2026-08-11T16:30:00+03:00"},
        )
        weather_tool = _FakeTool(
            "get_current_weather",
            {"temperature": {"value": 41.2, "unit": "°C"}},
        )
        provider = _FakeProvider(
            [
                {
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "time-1",
                            "name": "get_current_time",
                            "arguments": {"location": "Riyadh"},
                        },
                        {
                            "id": "weather-1",
                            "name": "get_current_weather",
                            "arguments": json.dumps(
                                {"location": "Riyadh"}
                            ),
                        },
                    ],
                },
                {
                    "content": json.dumps(
                        {
                            "action": "answer",
                            "answer": (
                                "It is 4:30 PM and the temperature "
                                "is 41.2 °C in Riyadh."
                            ),
                        }
                    ),
                    "tool_calls": [],
                },
            ]
        )
        agent = UtilityAgent(
            llm_provider=provider,
            tool_registry=_registry_with(time_tool, weather_tool),
        )
        state = build_initial_multi_agent_state(
            "What time is it in Riyadh and what is the weather?"
        )

        update = await agent(state)

        self.assertEqual(update["task_status"], TaskStatus.COMPLETED)
        self.assertEqual(update["active_agent"], AgentName.UTILITY)
        self.assertEqual(update["final_response"]["agent"], "utility")
        self.assertEqual(update["final_response"]["iterations"], 2)
        self.assertEqual(len(update["tool_history"]), 2)
        self.assertEqual(
            time_tool.calls,
            [{"location": "Riyadh"}],
        )
        self.assertEqual(
            weather_tool.calls,
            [{"location": "Riyadh"}],
        )
        self.assertEqual(len(provider.tool_results), 2)
        self.assertEqual(update["messages"][-1]["role"], "assistant")

    async def test_uses_provider_specific_roles(self):
        provider = _FakeProvider(
            [
                {
                    "content": json.dumps(
                        {"action": "answer", "answer": "Done"}
                    ),
                    "tool_calls": [],
                }
            ]
        )
        agent = UtilityAgent(
            llm_provider=provider,
            tool_registry=ToolRegistry(),
        )
        state = build_initial_multi_agent_state("Explain this utility")
        state["messages"] = [
            {"role": "user", "content": "Previous question"},
            {"role": "assistant", "content": "Previous answer"},
        ]

        await agent(state)

        roles = [
            message["role"]
            for message in provider.calls[0]["messages"]
        ]
        self.assertEqual(
            roles,
            ["SYSTEM", "USER", "CHATBOT", "USER"],
        )

    async def test_out_of_scope_response_returns_handoff(self):
        provider = _FakeProvider(
            [
                {
                    "content": json.dumps(
                        {
                            "action": "handoff",
                            "handoff_reason": "project_knowledge",
                        }
                    ),
                    "tool_calls": [],
                }
            ]
        )
        agent = UtilityAgent(
            llm_provider=provider,
            tool_registry=ToolRegistry(),
        )

        update = await agent(
            build_initial_multi_agent_state("Summarize my report")
        )

        self.assertEqual(update["task_status"], TaskStatus.RUNNING)
        self.assertEqual(update["handoff_count"], 1)
        self.assertEqual(update["visited_agents"], [AgentName.UTILITY])
        self.assertEqual(update["handoff_reason"], "project_knowledge")

    async def test_unknown_tool_is_returned_to_llm_as_a_safe_failure(self):
        provider = _FakeProvider(
            [
                {
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "bad-1",
                            "name": "unknown_tool",
                            "arguments": {},
                        }
                    ],
                },
                {
                    "content": json.dumps(
                        {
                            "action": "answer",
                            "answer": "I could not use that tool.",
                        }
                    ),
                    "tool_calls": [],
                },
            ]
        )
        agent = UtilityAgent(
            llm_provider=provider,
            tool_registry=ToolRegistry(),
        )

        update = await agent(
            build_initial_multi_agent_state("Use a tool")
        )

        self.assertEqual(update["task_status"], TaskStatus.COMPLETED)
        self.assertFalse(
            update["tool_history"][0]["result"]["success"]
        )
        self.assertEqual(
            update["tool_history"][0]["result"]["error"],
            "Unknown utility tool.",
        )

    async def test_iteration_limit_stops_repeated_tool_calls(self):
        provider = _FakeProvider(
            [
                {
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "time-1",
                            "name": "get_current_time",
                            "arguments": {"location": "Riyadh"},
                        }
                    ],
                }
            ]
        )
        tool = _FakeTool("get_current_time", {"time": "now"})
        agent = UtilityAgent(
            llm_provider=provider,
            tool_registry=_registry_with(tool),
            max_iterations=1,
        )

        update = await agent(
            build_initial_multi_agent_state("Time in Riyadh?")
        )

        self.assertEqual(update["task_status"], TaskStatus.FAILED)
        self.assertEqual(
            update["error"],
            "The utility agent exceeded the iteration limit.",
        )

    async def test_invalid_final_response_is_rejected(self):
        provider = _FakeProvider(
            [{"content": "plain text", "tool_calls": []}]
        )
        agent = UtilityAgent(
            llm_provider=provider,
            tool_registry=ToolRegistry(),
        )

        update = await agent(
            build_initial_multi_agent_state("Hello")
        )

        self.assertEqual(update["task_status"], TaskStatus.FAILED)
        self.assertEqual(
            update["error"],
            "The utility agent returned an invalid response.",
        )

    async def test_non_object_provider_response_is_rejected(self):
        agent = UtilityAgent(
            llm_provider=_FakeProvider(["not-an-object"]),
            tool_registry=ToolRegistry(),
        )

        update = await agent(build_initial_multi_agent_state("Hello"))

        self.assertEqual(update["task_status"], TaskStatus.FAILED)
        self.assertEqual(
            update["error"],
            "The utility agent returned an invalid response.",
        )

    async def test_malformed_tool_history_is_rejected(self):
        state = build_initial_multi_agent_state("Time in Riyadh?")
        state["tool_history"] = "not-a-list"
        agent = UtilityAgent(
            llm_provider=_FakeProvider([]),
            tool_registry=ToolRegistry(),
        )

        update = await agent(state)

        self.assertEqual(update["task_status"], TaskStatus.FAILED)
        self.assertEqual(update["error"], "tool_history must be a list.")

    def test_limits_must_be_positive(self):
        invalid_configs = [
            {"max_iterations": 0},
            {"max_tool_calls_per_iteration": 0},
            {"max_memory_messages": 1},
        ]

        for config in invalid_configs:
            with self.subTest(config=config):
                with self.assertRaises(ValueError):
                    UtilityAgent(
                        llm_provider=_FakeProvider([]),
                        tool_registry=ToolRegistry(),
                        **config,
                    )


if __name__ == "__main__":
    unittest.main()
