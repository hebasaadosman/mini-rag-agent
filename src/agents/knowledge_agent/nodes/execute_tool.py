import json
from json import JSONDecodeError
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.config import get_stream_writer

from ..state import KnowledgeAgentState


class ExecuteToolNode:
    """
    Execute all tool calls requested by the LLM.

    This node does not update conversation messages.
    It stores normalized executions temporarily in:

        pending_tool_executions
    """

    def __init__(
        self,
        *,
        tool_registry,
    ) -> None:
        self._tool_registry = tool_registry

    async def __call__(
        self,
        state: KnowledgeAgentState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        model_response = (
            state.get("model_response")
            or {}
        )

        tool_calls = (
            model_response.get("tool_calls")
            or []
        )

        pending_executions: list[
            dict[str, Any]
        ] = []
        streaming = bool(
            config.get("configurable", {}).get("streaming")
        )
        writer = get_stream_writer() if streaming else None

        for tool_index, tool_call in enumerate(
            tool_calls,
            start=1,
        ):
            tool_call_id = (
                tool_call.get("id")
                or (
                    "missing-call-id-"
                    f"{state.get('iterations', 0)}-"
                    f"{tool_index}"
                )
            )

            tool_name = (
                tool_call.get("name")
                or "unknown_tool"
            )

            raw_arguments = tool_call.get(
                "arguments"
            )

            tool_arguments: dict[str, Any] = {}

            if writer is not None:
                writer(
                    {
                        "kind": "tool_started",
                        "tool_name": tool_name,
                        "iteration": state.get("iterations", 0),
                    }
                )

            try:
                tool_arguments = (
                    self._parse_tool_arguments(
                        raw_arguments
                    )
                )

                if tool_name == "unknown_tool":
                    raise ValueError(
                        "The model returned a tool "
                        "call without a tool name."
                    )

                execution_result = (
                    await self._tool_registry
                    .execute(
                        name=tool_name,
                        arguments=tool_arguments,
                    )
                )
                print(
                    "\nREAD TOOL DEBUG:",
                    {
                        "tool_name": tool_name,
                        "arguments": tool_arguments,
                        "execution_result": execution_result,
                    },
                )
            except Exception as exc:
                execution_result = {
                    "success": False,
                    "tool_name": tool_name,
                    "result": None,
                    "error": str(exc),
                }
                print(
                        "TOOL EXECUTION ERROR:",
                        {
                            "tool_name": tool_name,
                            "arguments": tool_arguments,
                            "error": str(exc),
                        },
                    )
            if writer is not None:
                writer(
                    {
                        "kind": "tool_completed",
                        "tool_name": tool_name,
                        "iteration": state.get("iterations", 0),
                        "success": bool(execution_result.get("success")),
                    }
                )
            pending_executions.append(
                {
                    "iteration": state.get(
                        "iterations",
                        0,
                    ),
                    "tool_index": tool_index,
                    "tool_call_id": tool_call_id,
                    "tool_name": tool_name,
                    "arguments": tool_arguments,
                    "execution_result": (
                        execution_result
                    ),
                }
            )

        return {
            "pending_tool_executions": (
                pending_executions
            ),
        }

    @staticmethod
    def _parse_tool_arguments(
        raw_arguments: (
            str
            | dict[str, Any]
            | None
        ),
    ) -> dict[str, Any]:
        """
        OpenAI usually returns a JSON string.
        Other providers may return a dictionary.
        """

        if raw_arguments is None:
            return {}

        if isinstance(
            raw_arguments,
            dict,
        ):
            return raw_arguments

        if isinstance(
            raw_arguments,
            str,
        ):
            try:
                parsed_arguments = json.loads(
                    raw_arguments
                )

            except JSONDecodeError as exc:
                raise ValueError(
                    "The model returned invalid "
                    "JSON tool arguments: "
                    f"{raw_arguments}"
                ) from exc

            if not isinstance(
                parsed_arguments,
                dict,
            ):
                raise ValueError(
                    "Tool arguments must be "
                    "a JSON object."
                )

            return parsed_arguments

        raise TypeError(
            "Tool arguments must be a JSON "
            "string, dictionary, or None."
        )
