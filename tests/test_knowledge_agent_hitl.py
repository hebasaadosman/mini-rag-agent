import json
import unittest
from enum import Enum

try:
    from langgraph.checkpoint.memory import InMemorySaver

    from agents.knowledge_agent.graph import KnowledgeAgentGraph
    from agents.knowledge_agent.nodes import RequestClarificationNode
    from agents.tools import RequestClarificationTool, ToolRegistry
except ModuleNotFoundError as exc:
    if exc.name not in {"langgraph", "langchain_core"}:
        raise
    InMemorySaver = None
    KnowledgeAgentGraph = None
    RequestClarificationNode = None
    RequestClarificationTool = None
    ToolRegistry = None


class _Role(Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class _Enums:
    SYSTEM = _Role.SYSTEM
    USER = _Role.USER
    ASSISTANT = _Role.ASSISTANT


class _FakeLLMProvider:
    enums = _Enums()

    def __init__(self):
        self._responses = [
            {
                "content": "",
                "tool_calls": [
                    {
                        "id": "clarify-1",
                        "name": "request_clarification",
                        "arguments": json.dumps(
                            {
                                "question": "Which report do you mean?",
                                "options": ["Sales", "Finance"],
                                "reason": "Multiple reports match.",
                            }
                        ),
                    }
                ],
                "finish_reason": "tool_calls",
            },
            {
                "content": json.dumps(
                    {
                        "answer": "You selected the Sales report.",
                        "used_chunk_ids": [],
                    }
                ),
                "tool_calls": [],
                "finish_reason": "stop",
            },
        ]

    def construct_prompt(self, prompt, role):
        return {"role": role, "content": prompt}

    def generate_tool_response(self, **kwargs):
        return self._responses.pop(0)

    def construct_assistant_tool_message(self, response):
        for tool_call in response.get("tool_calls", []):
            if not isinstance(tool_call.get("arguments"), str):
                raise TypeError("Tool arguments must be a JSON string.")

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


class _ImplicitClarificationLLMProvider(_FakeLLMProvider):
    def __init__(self):
        self._responses = [
            {
                "content": json.dumps(
                    {
                        "answer": (
                            "يرجى تزويدي باسم التقرير الذي ترغب في تلخيصه."
                        ),
                        "used_chunk_ids": [],
                    },
                    ensure_ascii=False,
                ),
                "tool_calls": [],
                "finish_reason": "stop",
            },
            {
                "content": json.dumps(
                    {
                        "answer": "تم اختيار المستند المحدد.",
                        "used_chunk_ids": [],
                    },
                    ensure_ascii=False,
                ),
                "tool_calls": [],
                "finish_reason": "stop",
            },
        ]


class _StructuredClarificationLLMProvider(_FakeLLMProvider):
    def __init__(self):
        self._responses = [
            {
                "content": json.dumps(
                    {
                        "response_type": "clarification",
                        "question": "Which report should I summarize?",
                        "options": ["Sales", "Finance"],
                    }
                ),
                "tool_calls": [],
                "finish_reason": "stop",
            },
            {
                "content": json.dumps(
                    {
                        "response_type": "answer",
                        "answer": "The selected report was summarized.",
                        "used_chunk_ids": [],
                    }
                ),
                "tool_calls": [],
                "finish_reason": "stop",
            },
        ]


@unittest.skipUnless(InMemorySaver, "langgraph is not installed")
class KnowledgeAgentHITLTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        registry = ToolRegistry()
        registry.register_tool(RequestClarificationTool())
        self.graph = KnowledgeAgentGraph(
            project_id=7,
            llm_provider=_FakeLLMProvider(),
            tool_registry=registry,
            checkpointer=InMemorySaver(),
        )

    async def test_graph_pauses_and_resumes_clarification(self):
        interrupted = await self.graph.run(
            thread_id="thread-1",
            user_message="Summarize the report",
            system_prompt="Use tools when required.",
        )

        self.assertEqual(interrupted["status"], "clarification_required")
        self.assertEqual(
            interrupted["clarification"]["question"],
            "Which report do you mean?",
        )

        with self.assertRaisesRegex(
            ValueError,
            "waiting for clarification",
        ):
            await self.graph.run(
                thread_id="thread-1",
                user_message="Start a different request",
                system_prompt="Use tools when required.",
            )

        completed = await self.graph.resume(
            thread_id="thread-1",
            response="Sales",
        )

        self.assertEqual(completed["status"], "completed")
        self.assertEqual(
            completed["answer"],
            "You selected the Sales report.",
        )

    async def test_invalid_option_does_not_resume_graph(self):
        interrupted = await self.graph.run(
            thread_id="invalid-option-thread",
            user_message="Summarize the report",
            system_prompt="Use tools when required.",
        )

        rejected = await self.graph.resume(
            thread_id="invalid-option-thread",
            response="not-a-real-option.pdf",
        )

        self.assertEqual(rejected["status"], "clarification_required")
        self.assertEqual(
            rejected["clarification"]["options"],
            interrupted["clarification"]["options"],
        )
        self.assertEqual(
            rejected["interrupt_id"],
            interrupted["interrupt_id"],
        )

        completed = await self.graph.resume(
            thread_id="invalid-option-thread",
            response="Sales",
        )
        self.assertEqual(completed["status"], "completed")

    async def test_resume_rejects_thread_without_interrupt(self):
        with self.assertRaisesRegex(ValueError, "No pending clarification"):
            await self.graph.resume(
                thread_id="unknown-thread",
                response="Sales",
            )

    def test_normal_answer_ending_with_question_routes_to_final(self):
        route = KnowledgeAgentGraph._route_after_llm(
            {
                "model_response": {
                    "content": json.dumps(
                        {
                            "response_type": "answer",
                            "answer": "Hello! How can I help you?",
                            "used_chunk_ids": [],
                        }
                    ),
                    "tool_calls": [],
                }
            }
        )
        self.assertEqual(route, "final")

    def test_structured_clarification_routes_to_interrupt(self):
        route = KnowledgeAgentGraph._route_after_llm(
            {
                "model_response": {
                    "content": json.dumps(
                        {
                            "response_type": "clarification",
                            "question": "Which report do you mean?",
                            "options": ["Sales", "Finance"],
                        }
                    ),
                    "tool_calls": [],
                }
            }
        )
        self.assertEqual(route, "clarify")

    def test_invalid_model_labels_do_not_replace_real_options(self):
        selected = RequestClarificationNode._select_stable_options(
            raw_options=["First report", "Second report"],
            previous_options=["a.pdf", "b.pdf"],
            asset_options=["a.pdf", "b.pdf"],
        )

        self.assertEqual(selected, ["a.pdf", "b.pdf"])

    def test_search_asset_matches_become_real_clarification_options(self):
        options = RequestClarificationNode._asset_options_from_history(
            [
                {
                    "tool_name": "search_assets_by_name",
                    "execution_result": {
                        "result": {
                            "assets": [
                                {"asset_name": "first.pdf"},
                                {"asset_name": "second.pdf"},
                            ]
                        }
                    },
                }
            ]
        )

        self.assertEqual(options, ["first.pdf", "second.pdf"])

    async def test_structured_clarification_pauses_and_resumes(self):
        registry = ToolRegistry()
        registry.register_tool(RequestClarificationTool())
        graph = KnowledgeAgentGraph(
            project_id=7,
            llm_provider=_StructuredClarificationLLMProvider(),
            tool_registry=registry,
            checkpointer=InMemorySaver(),
        )

        interrupted = await graph.run(
            thread_id="implicit-thread",
            user_message="لخص التقرير",
            system_prompt="Use tools when required.",
        )
        self.assertEqual(interrupted["status"], "clarification_required")
        self.assertEqual(
            interrupted["clarification"]["question"],
            "Which report should I summarize?",
        )

        completed = await graph.resume(
            thread_id="implicit-thread",
            response="Sales",
        )
        self.assertEqual(completed["status"], "completed")
