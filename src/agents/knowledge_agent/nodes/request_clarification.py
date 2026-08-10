import json
from json import JSONDecodeError
from typing import Any

from langgraph.types import interrupt

from ..state import KnowledgeAgentState


class RequestClarificationNode:
    """Pause the graph and incorporate the user's clarification."""

    TOOL_NAME = "request_clarification"

    def __init__(self, *, llm_provider) -> None:
        self._llm_provider = llm_provider

    async def __call__(
        self,
        state: KnowledgeAgentState,
    ) -> dict[str, Any]:
        model_response = state.get("model_response") or {}
        tool_call = self._find_clarification_call(
            model_response.get("tool_calls") or []
        )
        if tool_call is None:
            clarification = self._extract_clarification_from_content(
                model_response.get("content")
            )
            tool_call = {
                "id": "implicit-clarification",
                "name": self.TOOL_NAME,
                "arguments": json.dumps(
                    clarification,
                    ensure_ascii=False,
                ),
            }
            model_response = {
                **model_response,
                "content": "",
                "tool_calls": [tool_call],
            }
        arguments = self._parse_arguments(
            tool_call.get("arguments")
        )
        question = str(arguments.get("question") or "").strip()

        if not question:
            return {
                "success": False,
                "error": "The clarification question cannot be empty.",
            }

        raw_options = arguments.get("options") or []
        if not isinstance(raw_options, list):
            raw_options = []

        previous_options = state.get("clarification_options") or []
        asset_options = self._asset_options_from_history(
            state.get("tool_history") or []
        )

        # Keep machine-selectable values stable across an invalid resume.
        # The model may otherwise replace real filenames with labels such
        # as "first report", which the next resume cannot resolve safely.
        raw_options = self._select_stable_options(
            raw_options=raw_options,
            previous_options=previous_options,
            asset_options=asset_options,
        )

        options = [
            str(option).strip()
            for option in raw_options
            if str(option).strip()
        ]

        human_response = interrupt(
            {
                "type": "clarification",
                "question": question,
                "options": options,
            }
        )
        normalized_response = self._normalize_response(human_response)

        if not normalized_response:
            return {
                "success": False,
                "error": "The clarification response cannot be empty.",
            }

        messages = list(state.get("messages", []))
        messages.append(
            self._llm_provider.construct_assistant_tool_message(
                model_response
            )
        )
        for pending_call in model_response.get("tool_calls") or []:
            is_clarification = pending_call is tool_call
            result = (
                {
                    "success": True,
                    "response": normalized_response,
                }
                if is_clarification
                else {
                    "success": False,
                    "skipped": True,
                    "error": (
                        "Tool execution was deferred until the "
                        "ambiguity was clarified."
                    ),
                }
            )
            messages.append(
                self._llm_provider.construct_tool_result_message(
                    tool_call_id=(
                        pending_call.get("id")
                        or "missing-tool-call-id"
                    ),
                    tool_name=(
                        pending_call.get("name")
                        or "unknown_tool"
                    ),
                    result=result,
                )
            )

        return {
            "messages": messages,
            "model_response": None,
            "pending_tool_executions": [],
            "clarification_options": options,
            "error": None,
        }

    @classmethod
    def _find_clarification_call(
        cls,
        tool_calls: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        for tool_call in tool_calls:
            if tool_call.get("name") == cls.TOOL_NAME:
                return tool_call

        return None

    @staticmethod
    def _extract_clarification_from_content(
        content: Any,
    ) -> dict[str, Any]:
        raw_content = str(content or "").strip()
        try:
            parsed = json.loads(raw_content)
        except JSONDecodeError:
            return {"question": raw_content, "options": []}

        if isinstance(parsed, dict):
            question = parsed.get("question")
            if isinstance(question, str):
                options = parsed.get("options")
                return {
                    "question": question.strip(),
                    "options": options if isinstance(options, list) else [],
                }

            # Backward compatibility for older saved checkpoints.
            answer = parsed.get("answer")
            if isinstance(answer, str):
                return {"question": answer.strip(), "options": []}

        return {"question": raw_content, "options": []}

    @staticmethod
    def _parse_arguments(raw_arguments: Any) -> dict[str, Any]:
        if isinstance(raw_arguments, dict):
            return raw_arguments

        if isinstance(raw_arguments, str):
            try:
                parsed = json.loads(raw_arguments)
            except JSONDecodeError as exc:
                raise ValueError(
                    "The clarification arguments are not valid JSON."
                ) from exc

            if isinstance(parsed, dict):
                return parsed

        raise ValueError("Clarification arguments must be a JSON object.")

    @staticmethod
    def _normalize_response(response: Any) -> str:
        if isinstance(response, dict):
            response = response.get("response")

        return str(response or "").strip()

    @staticmethod
    def _asset_options_from_history(
        tool_history: list[dict[str, Any]],
    ) -> list[str]:
        for execution in reversed(tool_history):
            if execution.get("tool_name") != "list_project_assets":
                continue

            execution_result = execution.get("execution_result") or {}
            tool_result = execution_result.get("result") or {}
            assets = tool_result.get("assets") or []
            return [
                str(asset.get("asset_name") or "").strip()
                for asset in assets
                if str(asset.get("asset_name") or "").strip()
            ]

        return []

    @staticmethod
    def _select_stable_options(
        *,
        raw_options: list[Any],
        previous_options: list[str],
        asset_options: list[str],
    ) -> list[Any]:
        raw_values = set(map(str, raw_options))

        if previous_options and (
            not raw_options
            or not raw_values.intersection(previous_options)
        ):
            return previous_options

        if asset_options and (
            not raw_options
            or not raw_values.intersection(asset_options)
        ):
            return asset_options

        return raw_options
