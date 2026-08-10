from typing import Any

from .BaseTool import BaseTool


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register_tool(
        self,
        tool: BaseTool,
    ) -> None:
        if tool.name in self._tools:
            raise ValueError(
                f"Tool '{tool.name}' is already registered."
            )

        self._tools[tool.name] = tool

    def get_tool(
        self,
        name: str,
    ) -> BaseTool:
        tool = self._tools.get(name)

        if tool is None:
            raise KeyError(
                f"Unknown tool: '{name}'."
            )

        return tool

    def get_schemas(
        self,
    ) -> list[dict[str, Any]]:
        return [
            tool.schema
            for tool in self._tools.values()
        ]

    def list_tool_names(
        self,
    ) -> list[str]:
        return list(self._tools.keys())

    async def execute(
        self,
        *,
        name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        tool = self.get_tool(name)

        try:
            result = await tool.execute(
                **arguments
            )

            return {
                "success": True,
                "tool_name": name,
                "result": result,
                "error": None,
            }

        except TypeError as exc:
            return {
                "success": False,
                "tool_name": name,
                "result": None,
                "error": (
                    "Invalid arguments supplied to the tool: "
                    f"{exc}"
                ),
            }

        except Exception as exc:
            return {
                "success": False,
                "tool_name": name,
                "result": None,
                "error": str(exc),
            }