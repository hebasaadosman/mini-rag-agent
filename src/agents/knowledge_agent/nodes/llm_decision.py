import asyncio
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.config import get_stream_writer

from ..state import KnowledgeAgentState


class LLMDecisionNode:
    """
    Ask the LLM what should happen next.

    This node never executes tools.
    It only stores the model response.
    """

    def __init__(
        self,
        *,
        llm_provider,
        tool_registry,
        max_tokens: int = 2000,
        temperature: float = 0,
    ) -> None:
        self._llm_provider = llm_provider
        self._tool_registry = tool_registry
        self._max_tokens = max_tokens
        self._temperature = temperature

    async def __call__(
        self,
        state: KnowledgeAgentState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        next_iteration = (
            state.get("iterations", 0) + 1
        )

        tool_choice =  "auto"
        

        streaming = bool(
            config.get("configurable", {}).get("streaming")
        )

        try:
            if streaming:
                writer = get_stream_writer()
                writer(
                    {
                        "kind": "status",
                        "stage": "thinking",
                        "iteration": next_iteration,
                    }
                )
                stream_method = getattr(
                    self._llm_provider,
                    "generate_tool_response_stream",
                    None,
                )
                if callable(stream_method):
                    model_response = await stream_method(
                        messages=state.get("messages", []),
                        tools=self._tool_registry.get_schemas(),
                        tool_choice=tool_choice,
                        max_tokens=self._max_tokens,
                        temperature=self._temperature,
                        on_content_delta=lambda content: writer(
                            {
                                "kind": "model_content_delta",
                                "content": content,
                            }
                        ),
                    )
                else:
                    model_response = await asyncio.to_thread(
                        self._llm_provider.generate_tool_response,
                        messages=state.get("messages", []),
                        tools=self._tool_registry.get_schemas(),
                        tool_choice=tool_choice,
                        max_tokens=self._max_tokens,
                        temperature=self._temperature,
                    )
                    content = str(model_response.get("content") or "")
                    if content:
                        writer(
                            {
                                "kind": "model_content_delta",
                                "content": content,
                            }
                        )
            else:
                model_response = self._llm_provider.generate_tool_response(
                    messages=state.get(
                        "messages",
                        [],
                    ),
                    tools=(
                        self._tool_registry
                        .get_schemas()
                    ),
                    tool_choice=tool_choice,
                    max_tokens=self._max_tokens,
                    temperature=self._temperature,
                )
            print(
                "LLM RESPONSE:",
                {
                    "iteration": next_iteration,
                    "content": model_response.get("content"),
                    "tool_calls": model_response.get("tool_calls"),
                    "finish_reason": model_response.get(
                        "finish_reason"
                    ),
                },
            )

        except Exception as exc:
            return {
                "iterations": next_iteration,
                "model_response": None,
                "success": False,
                "error": (
                    "Failed to call the LLM: "
                    f"{exc}"
                ),
            }

        return {
            "iterations": next_iteration,
            "model_response": model_response,
            "finish_reason": (
                model_response.get(
                    "finish_reason"
                )
            ),
            "error": None,
        }
