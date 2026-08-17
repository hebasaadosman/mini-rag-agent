import unittest
from typing import Any

from agents.tools import (
    AllowlistToolExecutionGuard,
    BaseTool,
    ToolExecutionContext,
    ToolRegistry,
)


class _RecordingTool(BaseTool):
    name = "safe_tool"
    description = "Test-only tool."

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    @property
    def schema(self) -> dict[str, Any]:
        return {"type": "function", "function": {"name": self.name}}

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {"value": "ok"}


class ToolExecutionGuardTests(unittest.IsolatedAsyncioTestCase):
    async def test_allows_a_permitted_tool(self):
        tool = _RecordingTool()
        registry = ToolRegistry(
            execution_guard=AllowlistToolExecutionGuard(
                allowed_tools={"safe_tool"},
            )
        )
        registry.register_tool(tool)

        result = await registry.execute(
            name="safe_tool",
            arguments={"value": "hello"},
            context=ToolExecutionContext(project_id=1, thread_id="t-1"),
        )

        self.assertTrue(result["success"])
        self.assertEqual(tool.calls, [{"value": "hello"}])

    async def test_blocks_a_registered_tool_not_in_policy_before_execution(self):
        tool = _RecordingTool()
        registry = ToolRegistry(
            execution_guard=AllowlistToolExecutionGuard(
                allowed_tools={"other_tool"},
            )
        )
        registry.register_tool(tool)

        result = await registry.execute(
            name="safe_tool",
            arguments={},
        )

        self.assertFalse(result["success"])
        self.assertIn("Tool execution blocked", result["error"])
        self.assertEqual(tool.calls, [])

    async def test_approval_gated_tool_is_not_executed_without_trusted_context(self):
        tool = _RecordingTool()
        registry = ToolRegistry(
            execution_guard=AllowlistToolExecutionGuard(
                allowed_tools={"safe_tool"},
                approval_required_tools={"safe_tool"},
            )
        )
        registry.register_tool(tool)

        result = await registry.execute(name="safe_tool", arguments={})

        self.assertFalse(result["success"])
        self.assertIn("requires an approved action", result["error"])
        self.assertEqual(tool.calls, [])

    async def test_approval_gated_tool_accepts_only_server_supplied_approval_id(self):
        tool = _RecordingTool()
        registry = ToolRegistry(
            execution_guard=AllowlistToolExecutionGuard(
                allowed_tools={"safe_tool"},
                approval_required_tools={"safe_tool"},
            )
        )
        registry.register_tool(tool)

        result = await registry.execute(
            name="safe_tool",
            arguments={},
            context=ToolExecutionContext(approval_id="approval-123"),
        )

        self.assertTrue(result["success"])
        self.assertEqual(tool.calls, [{}])


if __name__ == "__main__":
    unittest.main()
