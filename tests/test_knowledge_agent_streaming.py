import asyncio
import json
import unittest
from enum import Enum

from langgraph.checkpoint.memory import InMemorySaver

from agents.knowledge_agent.graph import KnowledgeAgentGraph
from agents.knowledge_agent.streaming import (
    AnswerDeltaParser,
    encode_sse,
    with_heartbeat,
)
from agents.tools import RequestClarificationTool, ToolRegistry
from routes.agents import agents_router


class _Role(Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class _Enums:
    SYSTEM = _Role.SYSTEM
    USER = _Role.USER
    ASSISTANT = _Role.ASSISTANT


class _StreamingLLMProvider:
    enums = _Enums()

    def __init__(self, responses):
        self._responses = list(responses)

    def construct_prompt(self, prompt, role):
        return {"role": role, "content": prompt}

    def generate_tool_response(self, **kwargs):
        return self._responses.pop(0)

    async def generate_tool_response_stream(
        self,
        *,
        on_content_delta=None,
        **kwargs,
    ):
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        for fragment in response.pop("fragments", []):
            if on_content_delta is not None:
                on_content_delta(fragment)
            await asyncio.sleep(0)
        return response

    def construct_assistant_tool_message(self, response):
        return {
            "role": "assistant",
            "content": response.get("content", ""),
            "tool_calls": response.get("tool_calls", []),
        }

    def construct_tool_result_message(
        self,
        *,
        tool_call_id,
        tool_name,
        result,
    ):
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": tool_name,
            "content": json.dumps(result),
        }


def _answer_response(answer: str) -> dict:
    content = json.dumps(
        {
            "response_type": "answer",
            "answer": answer,
            "used_chunk_ids": [],
        },
        ensure_ascii=True,
    )
    split_points = (9, 27, 43, 61, len(content))
    fragments = []
    start = 0
    for end in split_points:
        fragments.append(content[start:end])
        start = end
    return {
        "content": content,
        "fragments": fragments,
        "tool_calls": [],
        "finish_reason": "stop",
    }


class _ToolRegistry:
    def get_schemas(self):
        return [
            {
                "type": "function",
                "function": {
                    "name": "lookup",
                    "description": "Look up test data.",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]

    async def execute(self, *, name, arguments):
        return {
            "success": True,
            "tool_name": name,
            "result": {"value": "found"},
            "error": None,
        }


class AnswerDeltaParserTests(unittest.TestCase):
    def test_extracts_escaped_answer_across_fragment_boundaries(self):
        expected = 'مرحبا\nقال: "أهلًا" 👋'
        raw = json.dumps(
            {"response_type": "answer", "answer": expected},
            ensure_ascii=True,
        )
        parser = AnswerDeltaParser()
        actual = []
        for character in raw:
            actual.extend(parser.feed(character))
        self.assertEqual("".join(actual), expected)

    def test_ignores_non_answer_json(self):
        parser = AnswerDeltaParser()
        self.assertEqual(
            parser.feed(
                '{"response_type":"clarification","question":"Which?"}'
            ),
            [],
        )

    def test_sse_encoder_uses_named_event_and_unicode_json(self):
        encoded = encode_sse(
            event="token",
            data={"content": "مرحبًا"},
        )
        self.assertEqual(
            encoded,
            'event: token\ndata: {"content":"مرحبًا"}\n\n',
        )

    def test_streaming_routes_are_registered(self):
        paths = {route.path for route in agents_router.routes}
        self.assertIn(
            "/api/v1/agents/knowledge/{project_id}/chat/stream",
            paths,
        )
        self.assertIn(
            "/api/v1/agents/knowledge/{project_id}/chat/resume/stream",
            paths,
        )


class KnowledgeAgentStreamingTests(unittest.IsolatedAsyncioTestCase):
    async def test_heartbeat_is_emitted_while_the_agent_is_idle(self):
        async def slow_events():
            await asyncio.sleep(0.03)
            yield {"event": "completed", "data": {"success": True}}

        events = [
            event
            async for event in with_heartbeat(
                slow_events(),
                interval_seconds=0.01,
            )
        ]
        self.assertEqual(events[0]["event"], "heartbeat")
        self.assertEqual(events[-1]["event"], "completed")

    async def test_streams_answer_tokens_and_terminal_result(self):
        expected = "الإجابة تصل تدريجيًا."
        graph = KnowledgeAgentGraph(
            project_id=7,
            llm_provider=_StreamingLLMProvider(
                [_answer_response(expected)]
            ),
            tool_registry=ToolRegistry(),
            checkpointer=InMemorySaver(),
        )

        events = [
            event
            async for event in graph.stream(
                thread_id="stream-thread",
                user_message="أجبني",
                system_prompt="Answer safely.",
            )
        ]

        self.assertIn("status", [event["event"] for event in events])
        token_text = "".join(
            event["data"]["content"]
            for event in events
            if event["event"] == "token"
        )
        self.assertEqual(token_text, expected)
        self.assertEqual(events[-1]["event"], "result")
        self.assertEqual(events[-1]["data"]["status"], "completed")
        self.assertEqual(events[-1]["data"]["answer"], expected)

    async def test_streams_safe_tool_lifecycle_events(self):
        tool_response = {
            "content": "",
            "fragments": [],
            "tool_calls": [
                {
                    "id": "tool-1",
                    "name": "lookup",
                    "arguments": "{}",
                }
            ],
            "finish_reason": "tool_calls",
        }
        graph = KnowledgeAgentGraph(
            project_id=7,
            llm_provider=_StreamingLLMProvider(
                [tool_response, _answer_response("Found it.")]
            ),
            tool_registry=_ToolRegistry(),
            checkpointer=InMemorySaver(),
        )

        events = [
            event
            async for event in graph.stream(
                thread_id="tool-stream",
                user_message="Look it up",
                system_prompt="Use tools.",
            )
        ]
        tool_events = [
            event for event in events if event["event"].startswith("tool_")
        ]
        self.assertEqual(
            [event["event"] for event in tool_events],
            ["tool_started", "tool_completed"],
        )
        self.assertEqual(tool_events[0]["data"]["tool_name"], "lookup")
        self.assertNotIn("arguments", tool_events[0]["data"])
        self.assertNotIn("result", tool_events[1]["data"])
        self.assertEqual(events[-1]["data"]["status"], "completed")

    async def test_provider_failure_becomes_terminal_failed_result(self):
        graph = KnowledgeAgentGraph(
            project_id=7,
            llm_provider=_StreamingLLMProvider(
                [RuntimeError("provider unavailable")]
            ),
            tool_registry=ToolRegistry(),
            checkpointer=InMemorySaver(),
        )

        events = [
            event
            async for event in graph.stream(
                thread_id="failed-stream",
                user_message="Answer",
                system_prompt="Answer safely.",
            )
        ]
        self.assertEqual(events[-1]["data"]["status"], "failed")
        self.assertIn("provider unavailable", events[-1]["data"]["error"])

    async def test_stream_pauses_and_stream_resume_completes(self):
        clarification_response = {
            "content": "",
            "fragments": [],
            "tool_calls": [
                {
                    "id": "clarify-1",
                    "name": "request_clarification",
                    "arguments": json.dumps(
                        {
                            "question": "Which report?",
                            "options": ["Sales", "Finance"],
                        }
                    ),
                }
            ],
            "finish_reason": "tool_calls",
        }
        provider = _StreamingLLMProvider(
            [
                clarification_response,
                _answer_response("Sales selected."),
            ]
        )
        registry = ToolRegistry()
        registry.register_tool(RequestClarificationTool())
        graph = KnowledgeAgentGraph(
            project_id=8,
            llm_provider=provider,
            tool_registry=registry,
            checkpointer=InMemorySaver(),
        )

        interrupted = [
            event
            async for event in graph.stream(
                thread_id="hitl-stream",
                user_message="Summarize the report",
                system_prompt="Use clarification.",
            )
        ]
        self.assertEqual(
            interrupted[-1]["data"]["status"],
            "clarification_required",
        )
        self.assertFalse(
            any(event["event"] == "token" for event in interrupted)
        )

        invalid = [
            event
            async for event in graph.stream_resume(
                thread_id="hitl-stream",
                response="Unknown",
            )
        ]
        self.assertEqual(
            invalid[-1]["data"]["status"],
            "clarification_required",
        )

        completed = [
            event
            async for event in graph.stream_resume(
                thread_id="hitl-stream",
                response="Sales",
            )
        ]
        self.assertEqual(completed[-1]["data"]["status"], "completed")
        self.assertEqual(completed[-1]["data"]["answer"], "Sales selected.")


if __name__ == "__main__":
    unittest.main()
