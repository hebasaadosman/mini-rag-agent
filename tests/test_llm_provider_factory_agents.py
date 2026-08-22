import json
import unittest
from enum import Enum

from langgraph.checkpoint.memory import InMemorySaver

from agents.multi_agent import MultiAgentRuntime
from agents.tools import SendEmailTool
from stores.llm.LLMProviderFactory import LLMProviderFactory


class _Role(Enum):
    SYSTEM = "SYSTEM"
    USER = "USER"
    ASSISTANT = "CHATBOT"


class _Provider:
    enums = _Role

    def __init__(self):
        self._responses = iter(
            [
                json.dumps(
                    {
                        "route": "general",
                        "reason": "general_conversation",
                        "confidence": 0.99,
                    }
                ),
                json.dumps(
                    {
                        "action": "answer",
                        "answer": "Good morning!",
                    }
                ),
                json.dumps(
                    {
                        "entity_types": ["greeting"],
                        "embedded_assumptions": [],
                        "relationship_valid": True,
                        "verdict": "The greeting response is appropriate.",
                        "action": "answer",
                        "answer": "Good morning!",
                        "question": None,
                        "options": [],
                    }
                ),
            ]
        )

    def construct_prompt(self, prompt, role):
        return {"role": role, "content": prompt}

    def generate_text(self, *args, **kwargs):
        return next(self._responses)


class _KnowledgeAgent:
    async def run(self, **kwargs):
        raise AssertionError("Knowledge should not run in this test.")

    async def resume(self, **kwargs):
        raise AssertionError("Knowledge should not resume in this test.")


class _EmailGateway:
    async def send_email(self, **kwargs):
        return {"message_id": "factory-agent-test"}


def _runtime(*, send_email_tool=True):
    factory = LLMProviderFactory(config={})
    tool = (
        SendEmailTool(_EmailGateway())
        if send_email_tool
        else None
    )
    return factory.create_multi_agent_runtime(
        llm_provider=_Provider(),
        knowledge_agent_factory=(
            lambda project_id, checkpoint_key: _KnowledgeAgent()
        ),
        send_email_tool=tool,
        checkpointer=InMemorySaver(),
    )


class LLMProviderFactoryAgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_existing_factory_builds_the_multi_agent_runtime(self):
        runtime = _runtime()

        result = await runtime.chat(
            thread_id="existing-factory-001",
            message="Good morning",
            project_id=1,
            checkpoint_key="test:existing-factory-001",
        )

        self.assertIsInstance(runtime, MultiAgentRuntime)
        self.assertEqual(result["agent"], "general")
        self.assertEqual(result["answer"], "Good morning!")

    async def test_disabled_smtp_does_not_break_general_agent(self):
        runtime = _runtime(send_email_tool=False)

        result = await runtime.chat(
            thread_id="existing-factory-002",
            message="Good morning",
            project_id=1,
            checkpoint_key="test:existing-factory-002",
        )

        self.assertEqual(result["status"], "completed")

    def test_rejects_invalid_runtime_dependencies(self):
        factory = LLMProviderFactory(config={})
        with self.assertRaisesRegex(TypeError, "llm_provider"):
            factory.create_multi_agent_runtime(
                llm_provider=None,
                knowledge_agent_factory=(
                    lambda project_id, checkpoint_key: _KnowledgeAgent()
                ),
            )
        with self.assertRaisesRegex(TypeError, "knowledge_agent_factory"):
            factory.create_multi_agent_runtime(
                llm_provider=_Provider(),
                knowledge_agent_factory=None,
            )


if __name__ == "__main__":
    unittest.main()
