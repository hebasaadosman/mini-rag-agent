import json
import unittest
from enum import Enum

from agents.multi_agent import (
    AgentName,
    GeneralAgent,
    SupervisorAgent,
    SupervisorDestination,
    SupervisorRouter,
    build_initial_multi_agent_state,
)


class _Role(Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class _FakeProvider:
    enums = _Role

    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def construct_prompt(self, prompt, role):
        return {"role": role, "content": prompt}

    def generate_text(self, prompt, chat_history=None, **kwargs):
        self.calls.append(
            {
                "prompt": prompt,
                "chat_history": chat_history,
            }
        )
        return next(self.responses)


class MultiAgentHandoffFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_general_handoff_returns_to_supervisor_then_utility(self):
        supervisor_provider = _FakeProvider(
            [
                json.dumps(
                    {
                        "route": "general",
                        "reason": "general_conversation",
                        "confidence": 0.7,
                    }
                ),
                json.dumps(
                    {
                        "route": "utility",
                        "reason": "external_information",
                        "confidence": 0.99,
                    }
                ),
            ]
        )
        general_provider = _FakeProvider(
            [
                json.dumps(
                    {
                        "action": "handoff",
                        "handoff_reason": "external_information",
                    }
                ),
                json.dumps(
                    {
                        "entity_types": ["city", "weather"],
                        "embedded_assumptions": [],
                        "relationship_valid": True,
                        "verdict": "Weather requires current external data.",
                        "action": "handoff",
                        "answer": None,
                        "handoff_reason": "external_information",
                        "question": None,
                        "options": [],
                    }
                ),
            ]
        )
        supervisor = SupervisorAgent(
            llm_provider=supervisor_provider
        )
        general = GeneralAgent(llm_provider=general_provider)
        state = build_initial_multi_agent_state(
            "What is the weather in Riyadh?"
        )

        state.update(await supervisor(state))
        self.assertEqual(
            SupervisorRouter.route(state),
            SupervisorDestination.GENERAL,
        )

        state.update(await general(state))
        self.assertEqual(state["visited_agents"], [AgentName.GENERAL])
        self.assertIsNone(state["supervisor_decision"])

        state.update(await supervisor(state))
        self.assertEqual(
            SupervisorRouter.route(state),
            SupervisorDestination.UTILITY,
        )

        retry_system_prompt = (
            supervisor_provider.calls[1]["chat_history"][0]["content"]
        )
        self.assertIn(
            "Specialists already tried: general",
            retry_system_prompt,
        )

    async def test_general_handoff_can_route_to_email(self):
        supervisor_provider = _FakeProvider(
            [
                json.dumps(
                    {
                        "route": "general",
                        "reason": "general_conversation",
                        "confidence": 0.7,
                    }
                ),
                json.dumps(
                    {
                        "route": "email",
                        "reason": "action_required",
                        "confidence": 0.99,
                    }
                ),
            ]
        )
        general_provider = _FakeProvider(
            [
                json.dumps(
                    {
                        "action": "handoff",
                        "handoff_reason": "action_required",
                    }
                ),
                json.dumps(
                    {
                        "entity_types": ["recipient", "email action"],
                        "embedded_assumptions": [],
                        "relationship_valid": True,
                        "verdict": "Sending email requires an action specialist.",
                        "action": "handoff",
                        "answer": None,
                        "handoff_reason": "action_required",
                        "question": None,
                        "options": [],
                    }
                ),
            ]
        )
        supervisor = SupervisorAgent(
            llm_provider=supervisor_provider
        )
        general = GeneralAgent(llm_provider=general_provider)
        state = build_initial_multi_agent_state(
            "Send a project update email to Ahmed"
        )

        state.update(await supervisor(state))
        self.assertEqual(
            SupervisorRouter.route(state),
            SupervisorDestination.GENERAL,
        )

        state.update(await general(state))
        state.update(await supervisor(state))

        self.assertEqual(
            SupervisorRouter.route(state),
            SupervisorDestination.EMAIL,
        )


if __name__ == "__main__":
    unittest.main()
