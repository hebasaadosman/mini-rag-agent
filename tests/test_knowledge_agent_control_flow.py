import unittest

try:
    from agents.knowledge_agent.graph import KnowledgeAgentGraph
    from agents.knowledge_agent.nodes.execute_tool import ExecuteToolNode
except ModuleNotFoundError as exc:
    if exc.name != "langgraph":
        raise
    KnowledgeAgentGraph = None
    ExecuteToolNode = None


@unittest.skipUnless(KnowledgeAgentGraph, "langgraph is not installed")
class KnowledgeAgentControlFlowTests(unittest.TestCase):
    def test_graph_routes_after_llm(self):
        cases = [
            ({"error": "failed"}, "failure"),
            ({"model_response": {"tool_calls": []}}, "final"),
            (
                {
                    "model_response": {
                        "content": '{"answer": "Which report do you mean?"}',
                        "tool_calls": [],
                    }
                },
                "final",
            ),
            (
                {
                    "model_response": {
                        "content": (
                            '{"answer": "يرجى تزويدي باسم التقرير '
                            'الذي ترغب في تلخيصه."}'
                        ),
                        "tool_calls": [],
                    }
                },
                "final",
            ),
            (
                {
                    "model_response": {
                        "tool_calls": [
                            {"name": "request_clarification"},
                        ],
                    },
                    "iterations": 1,
                    "max_iterations": 5,
                },
                "clarify",
            ),
            (
                {
                    "model_response": {"tool_calls": [{"name": "search"}]},
                    "iterations": 1,
                    "max_iterations": 5,
                },
                "tools",
            ),
            (
                {
                    "model_response": {"tool_calls": [{"name": "search"}]},
                    "iterations": 5,
                    "max_iterations": 5,
                },
                "failure",
            ),
            (
                {
                    "model_response": {
                        "tool_calls": [
                            {"name": "request_clarification"},
                        ],
                    },
                    "iterations": 5,
                    "max_iterations": 5,
                },
                "failure",
            ),
            (
                {
                    "model_response": {
                        "content": (
                            '{"answer": "Available: report-a.pdf and '
                            'report-b.pdf. Which one?"}'
                        ),
                        "tool_calls": [],
                    },
                    "tool_history": [
                        {
                            "tool_name": "list_project_assets",
                            "execution_result": {
                                "result": {
                                    "assets": [
                                        {"asset_name": "report-a.pdf"},
                                        {"asset_name": "report-b.pdf"},
                                    ]
                                }
                            },
                        }
                    ],
                },
                "clarify",
            ),
        ]

        for state, expected_route in cases:
            with self.subTest(expected_route=expected_route):
                self.assertEqual(
                    KnowledgeAgentGraph._route_after_llm(state),
                    expected_route,
                )

    def test_tool_arguments_accept_json_object(self):
        self.assertEqual(
            ExecuteToolNode._parse_tool_arguments('{"limit": 5}'),
            {"limit": 5},
        )

    def test_tool_arguments_reject_non_object_json(self):
        with self.assertRaisesRegex(ValueError, "JSON object"):
            ExecuteToolNode._parse_tool_arguments("[1, 2]")
