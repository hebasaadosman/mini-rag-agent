import json
import unittest
from enum import Enum

try:
    from langgraph.checkpoint.memory import InMemorySaver

    from agents.knowledge_agent.graph import KnowledgeAgentGraph
    from agents.tools import ToolRegistry
except ModuleNotFoundError as exc:
    if exc.name not in {"langgraph", "langchain_core"}:
        raise
    InMemorySaver = None
    KnowledgeAgentGraph = None
    ToolRegistry = None


class _Role(Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class _Enums:
    SYSTEM = _Role.SYSTEM
    USER = _Role.USER
    ASSISTANT = _Role.ASSISTANT


class _MemoryLLMProvider:
    enums = _Enums()

    def __init__(self):
        self.calls = []

    def construct_prompt(self, prompt, role):
        return {"role": role, "content": prompt}

    def generate_tool_response(self, *, messages, **kwargs):
        self.calls.append(list(messages))
        user_messages = [
            message["content"]
            for message in messages
            if message.get("role") == "user"
        ]
        answer = (
            "I remember the previous turn."
            if len(user_messages) > 1
            else "I saved the first turn."
        )
        return {
            "content": json.dumps(
                {"answer": answer, "used_chunk_ids": []}
            ),
            "tool_calls": [],
            "finish_reason": "stop",
        }


@unittest.skipUnless(InMemorySaver, "langgraph is not installed")
class KnowledgeAgentMemoryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.provider = _MemoryLLMProvider()
        self.graph = KnowledgeAgentGraph(
            project_id=11,
            llm_provider=self.provider,
            tool_registry=ToolRegistry(),
            checkpointer=InMemorySaver(),
            max_memory_messages=5,
        )

    async def test_same_thread_reuses_conversation_messages(self):
        first = await self.graph.run(
            thread_id="memory-thread",
            user_message="My preferred language is Arabic.",
            system_prompt="You are helpful.",
        )
        second = await self.graph.run(
            thread_id="memory-thread",
            user_message="What language did I choose?",
            system_prompt="You are helpful.",
        )

        second_call = self.provider.calls[1]
        self.assertIn(
            "My preferred language is Arabic.",
            [message["content"] for message in second_call],
        )
        self.assertIn(
            "I saved the first turn.",
            [message["content"] for message in second_call],
        )
        self.assertEqual(first["memory_message_count"], 3)
        self.assertEqual(second["memory_message_count"], 5)

    async def test_memory_is_bounded_and_can_be_deleted(self):
        for index in range(3):
            result = await self.graph.run(
                thread_id="bounded-thread",
                user_message=f"Message {index}",
                system_prompt="You are helpful.",
            )
            self.assertLessEqual(result["memory_message_count"], 5)

        memory = await self.graph.get_memory(thread_id="bounded-thread")
        self.assertTrue(memory["exists"])
        self.assertLessEqual(memory["message_count"], 5)

        await self.graph.clear_memory(thread_id="bounded-thread")
        cleared = await self.graph.get_memory(thread_id="bounded-thread")
        self.assertFalse(cleared["exists"])
        self.assertEqual(cleared["message_count"], 0)

    async def test_different_thread_has_no_shared_context(self):
        await self.graph.run(
            thread_id="thread-a",
            user_message="Remember secret A.",
            system_prompt="You are helpful.",
        )
        await self.graph.run(
            thread_id="thread-b",
            user_message="What do you remember?",
            system_prompt="You are helpful.",
        )

        second_thread_messages = self.provider.calls[1]
        self.assertNotIn(
            "Remember secret A.",
            [message["content"] for message in second_thread_messages],
        )

    async def test_graph_can_still_run_without_checkpointer(self):
        graph = KnowledgeAgentGraph(
            project_id=11,
            llm_provider=_MemoryLLMProvider(),
            tool_registry=ToolRegistry(),
            checkpointer=None,
        )

        result = await graph.run(
            thread_id="stateless-evaluation",
            user_message="Evaluate this case.",
            system_prompt="You are helpful.",
        )

        self.assertEqual(result["status"], "completed")
