import json
from collections.abc import AsyncIterator
from json import JSONDecodeError
from typing import Any, Literal
from langgraph.graph import (
    END,
    START,
    StateGraph,
)
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command
from .nodes import (
    BuildStateNode,
    ExecuteToolNode,
    FailureNode,
    FinalAnswerNode,
    LLMDecisionNode,
    UpdateMessagesNode,
    RequestClarificationNode,
)
from .state import KnowledgeAgentState
from .streaming import AnswerDeltaParser

class KnowledgeAgentGraph:
    """
    LangGraph orchestration only.

    Business logic lives inside independent nodes.

    Flow:

        START
          ↓
        build_state
          ↓
        llm_decision
          ↓
        tools requested?
          ├── yes
          │     ↓
          │ execute_tool
          │     ↓
          │ update_messages
          │     ↓
          │ llm_decision
          │
          ├── no → final_answer → END
          │
          └── failure → END
    """

    def __init__(
    self,
        *,
        project_id: int,
        llm_provider,
        tool_registry,
        checkpointer=None,
        max_iterations: int = 5,
        max_memory_messages: int = 40,
    ) -> None:
        if max_iterations < 1:
            raise ValueError(
                "max_iterations must be at least 1."
            )
        if max_memory_messages < 5:
            raise ValueError(
                "max_memory_messages must be at least 5."
            )

        self._max_iterations = max_iterations
        self._checkpointer = checkpointer
        self._project_id = project_id
        self._max_memory_messages = max_memory_messages
        self._build_state_node = (
            BuildStateNode(
                llm_provider=llm_provider,
                max_memory_messages=max_memory_messages,
            )
        )

        self._llm_decision_node = (
            LLMDecisionNode(
                llm_provider=llm_provider,
                tool_registry=tool_registry,
            )
        )

        self._execute_tool_node = (
            ExecuteToolNode(
                tool_registry=tool_registry,
            )
        )

        self._update_messages_node = (
            UpdateMessagesNode(
                llm_provider=llm_provider,
            )
        )
        self._request_clarification_node = (
            RequestClarificationNode(
                llm_provider=llm_provider,
            )
        )

        self._final_answer_node = (
            FinalAnswerNode(
                llm_provider=llm_provider,
            )
        )

        self._failure_node = (
            FailureNode()
        )

        self._graph = self._build_graph()

    def _build_graph(self):
        builder = StateGraph(
            KnowledgeAgentState
        )

        builder.add_node(
            "build_state",
            self._build_state_node,
        )

        builder.add_node(
            "llm_decision",
            self._llm_decision_node,
        )

        builder.add_node(
            "execute_tool",
            self._execute_tool_node,
        )

        builder.add_node(
            "update_messages",
            self._update_messages_node,
        )

        builder.add_node(
            "final_answer",
            self._final_answer_node,
        )

        builder.add_node(
            "request_clarification",
            self._request_clarification_node,
        )

        builder.add_node(
            "failure",
            self._failure_node,
        )

        builder.add_edge(
            START,
            "build_state",
        )

        builder.add_conditional_edges(
            "build_state",
            self._route_after_build_state,
            {
                "continue": "llm_decision",
                "failure": "failure",
            },
        )

        builder.add_conditional_edges(
            "llm_decision",
            self._route_after_llm,
            {
                "tools": "execute_tool",
                "clarify": "request_clarification",
                "final": "final_answer",
                "failure": "failure",
            },
        )

        builder.add_edge(
            "request_clarification",
            "llm_decision",
        )

        builder.add_edge(
            "execute_tool",
            "update_messages",
        )

        builder.add_edge(
            "update_messages",
            "llm_decision",
        )

        builder.add_edge(
            "final_answer",
            END,
        )

        builder.add_edge(
            "failure",
            END,
        )

        return builder.compile(
            checkpointer=self._checkpointer,
        )

    @staticmethod
    def _route_after_build_state(
        state: KnowledgeAgentState,
    ) -> Literal[
        "continue",
        "failure",
    ]:
        if state.get("error"):
            return "failure"

        return "continue"

    @staticmethod
    def _route_after_llm(
        state: KnowledgeAgentState,
    ) -> Literal[
        "tools",
        "clarify",
        "final",
        "failure",
    ]:
        if state.get("error"):
            return "failure"

        model_response = (
            state.get("model_response")
            or {}
        )

        tool_calls = (
            model_response.get("tool_calls")
            or []
        )

        # Do not infer clarification from punctuation. A normal
        # conversational answer may legitimately end with a question.
        if not tool_calls:
            if KnowledgeAgentGraph._is_structured_clarification(
                model_response.get("content")
            ):
                return "clarify"
            if KnowledgeAgentGraph._requires_asset_selection(state):
                return "clarify"
            return "final"

        if (
            state.get("iterations", 0)
            >= state.get(
                "max_iterations",
                1,
            )
        ):
            return "failure"

        if any(
            tool_call.get("name") == "request_clarification"
            for tool_call in tool_calls
        ):
            return "clarify"

        return "tools"

    @staticmethod
    def _is_structured_clarification(content: Any) -> bool:
        raw_content = str(content or "").strip()
        if not raw_content:
            return False

        question = raw_content
        try:
            parsed = json.loads(raw_content)
        except JSONDecodeError:
            return False

        return (
            isinstance(parsed, dict)
            and parsed.get("response_type") == "clarification"
            and isinstance(parsed.get("question"), str)
            and bool(parsed["question"].strip())
        )

        # Kept unreachable temporarily for old checkpoint compatibility.
        if isinstance(parsed, dict):
            answer = parsed.get("answer")
            if not isinstance(answer, str):
                return False
            question = answer.strip()

        if not 0 < len(question) <= 500:
            return False

        if question.endswith(("?", "؟")):
            return True

        normalized_question = " ".join(question.lower().split())
        clarification_markers = (
            "يرجى تزويدي",
            "يرجى تحديد",
            "يرجى توضيح",
            "من فضلك حدد",
            "من فضلك وضح",
            "أحتاج إلى معرفة",
            "please provide",
            "please specify",
            "please clarify",
            "could you clarify",
            "which one do you mean",
        )

        return any(
            marker in normalized_question
            for marker in clarification_markers
        )

 
    def _build_config(
        self,
        thread_id: str,
        *,
        streaming: bool = False,
    ) -> RunnableConfig:
        scoped_thread_id = f"project:{self._project_id}:{thread_id}"

        return {
            "configurable": {
                "thread_id": scoped_thread_id,
                "streaming": streaming,
            },
            "run_name": "knowledge-agent",
            "tags": [
                "mini-rag",
                "knowledge-agent",
            ],
            "metadata": {
                "agent": "knowledge-agent",
                "agent_version": "v1",
                "project_id": self._project_id,
                "thread_id": thread_id,
                "max_iterations": self._max_iterations,
                "max_memory_messages": self._max_memory_messages,
            },
        }

    async def run(
        self,
        *,
        thread_id: str,
        user_message: str,
        system_prompt: str,
    ) -> dict[str, Any]:
        if not thread_id.strip():
            raise ValueError(
                "thread_id must not be empty."
            )

        initial_state: KnowledgeAgentState = {
            "user_message": user_message,
            "system_prompt": system_prompt,
            "max_iterations": self._max_iterations,
        }

        config = self._build_config(thread_id)

        if self._checkpointer is not None:
            snapshot = await self._graph.aget_state(config)
            if self._get_pending_interrupts(snapshot):
                raise ValueError(
                    "This thread is waiting for clarification. "
                    "Use the resume endpoint before sending a new message."
                )

        final_state = await self._graph.ainvoke(
            initial_state,
            config=config,
        )

        return self._serialize_result(final_state)

    async def stream(
        self,
        *,
        thread_id: str,
        user_message: str,
        system_prompt: str,
    ) -> AsyncIterator[dict[str, Any]]:
        if not thread_id.strip():
            raise ValueError("thread_id must not be empty.")

        initial_state: KnowledgeAgentState = {
            "user_message": user_message,
            "system_prompt": system_prompt,
            "max_iterations": self._max_iterations,
        }
        config = self._build_config(thread_id, streaming=True)

        if self._checkpointer is not None:
            snapshot = await self._graph.aget_state(config)
            if self._get_pending_interrupts(snapshot):
                raise ValueError(
                    "This thread is waiting for clarification. "
                    "Use the resume endpoint before sending a new message."
                )

        async for event in self._stream_graph(
            initial_state,
            config=config,
        ):
            yield event

    async def resume(
        self,
        *,
        thread_id: str,
        response: str,
    ) -> dict[str, Any]:
        normalized_response = response.strip()
        if not thread_id.strip():
            raise ValueError("thread_id must not be empty.")
        if not normalized_response:
            raise ValueError("response must not be empty.")

        config = self._build_config(thread_id)
        snapshot = await self._graph.aget_state(config)
        pending_interrupts = self._get_pending_interrupts(snapshot)
        if not pending_interrupts:
            raise ValueError(
                "No pending clarification exists for this thread."
            )

        current_interrupt = pending_interrupts[0]
        clarification = getattr(
            current_interrupt,
            "value",
            current_interrupt,
        )
        options = (
            clarification.get("options") or []
            if isinstance(clarification, dict)
            else []
        )
        if options:
            canonical_response = next(
                (
                    str(option).strip()
                    for option in options
                    if str(option).strip().casefold()
                    == normalized_response.casefold()
                ),
                None,
            )
            if canonical_response is None:
                values = snapshot.values or {}
                return {
                    "success": True,
                    "status": "clarification_required",
                    "answer": None,
                    "clarification": clarification,
                    "interrupt_id": getattr(
                        current_interrupt,
                        "id",
                        None,
                    ),
                    "used_chunk_ids": [],
                    "iterations": values.get("iterations", 0),
                    "tool_history": values.get("tool_history", []),
                    "messages": values.get("messages", []),
                    "memory_message_count": len(
                        values.get("messages", [])
                    ),
                    "error": None,
                }

            normalized_response = canonical_response

        final_state = await self._graph.ainvoke(
            Command(resume=normalized_response),
            config=config,
        )

        return self._serialize_result(final_state)

    async def stream_resume(
        self,
        *,
        thread_id: str,
        response: str,
    ) -> AsyncIterator[dict[str, Any]]:
        normalized_response = response.strip()
        if not thread_id.strip():
            raise ValueError("thread_id must not be empty.")
        if not normalized_response:
            raise ValueError("response must not be empty.")

        config = self._build_config(thread_id, streaming=True)
        snapshot = await self._graph.aget_state(config)
        pending_interrupts = self._get_pending_interrupts(snapshot)
        if not pending_interrupts:
            raise ValueError(
                "No pending clarification exists for this thread."
            )

        current_interrupt = pending_interrupts[0]
        clarification = getattr(
            current_interrupt,
            "value",
            current_interrupt,
        )
        options = (
            clarification.get("options") or []
            if isinstance(clarification, dict)
            else []
        )
        if options:
            canonical_response = next(
                (
                    str(option).strip()
                    for option in options
                    if str(option).strip().casefold()
                    == normalized_response.casefold()
                ),
                None,
            )
            if canonical_response is None:
                yield {
                    "event": "result",
                    "data": self._serialize_pending_snapshot(snapshot),
                }
                return
            normalized_response = canonical_response

        async for event in self._stream_graph(
            Command(resume=normalized_response),
            config=config,
        ):
            yield event

    async def _stream_graph(
        self,
        graph_input: KnowledgeAgentState | Command,
        *,
        config: RunnableConfig,
    ) -> AsyncIterator[dict[str, Any]]:
        answer_parser = AnswerDeltaParser()
        last_state: dict[str, Any] = {}

        async for part in self._graph.astream(
            graph_input,
            config=config,
            stream_mode=["custom", "values"],
            version="v2",
        ):
            part_type = part.get("type")
            data = part.get("data")

            if part_type == "values" and isinstance(data, dict):
                last_state = data
                continue

            if part_type != "custom" or not isinstance(data, dict):
                continue

            kind = data.get("kind")
            if kind == "status" and data.get("stage") == "thinking":
                # Each LLM iteration has its own structured JSON response.
                answer_parser = AnswerDeltaParser()

            if kind == "model_content_delta":
                answer_delta = "".join(
                    answer_parser.feed(str(data.get("content") or ""))
                )
                if answer_delta:
                    yield {
                        "event": "token",
                        "data": {"content": answer_delta},
                    }
                continue

            if kind in {
                "status",
                "tool_started",
                "tool_completed",
            }:
                yield {
                    "event": str(kind),
                    "data": {
                        key: value
                        for key, value in data.items()
                        if key != "kind"
                    },
                }

        if self._checkpointer is not None:
            snapshot = await self._graph.aget_state(config)
            if self._get_pending_interrupts(snapshot):
                result = self._serialize_pending_snapshot(snapshot)
            else:
                result = self._serialize_result(snapshot.values or last_state)
        else:
            result = self._serialize_result(last_state)

        yield {"event": "result", "data": result}

    async def get_memory(self, *, thread_id: str) -> dict[str, Any]:
        if not thread_id.strip():
            raise ValueError("thread_id must not be empty.")

        if self._checkpointer is None:
            return {
                "exists": False,
                "message_count": 0,
                "pending_clarification": False,
            }

        snapshot = await self._graph.aget_state(
            self._build_config(thread_id)
        )
        values = snapshot.values or {}
        messages = values.get("messages") or []

        return {
            "exists": bool(messages or snapshot.tasks),
            "message_count": len(messages),
            "pending_clarification": bool(
                self._get_pending_interrupts(snapshot)
            ),
        }

    async def clear_memory(self, *, thread_id: str) -> None:
        if not thread_id.strip():
            raise ValueError("thread_id must not be empty.")
        if self._checkpointer is None:
            raise RuntimeError("A checkpointer is required for memory.")

        await self._checkpointer.adelete_thread(
            self._get_scoped_thread_id(thread_id)
        )

    def _get_scoped_thread_id(self, thread_id: str) -> str:
        return f"project:{self._project_id}:{thread_id}"

    @staticmethod
    def _requires_asset_selection(state: KnowledgeAgentState) -> bool:
        options = KnowledgeAgentGraph._asset_options_from_history(
            state.get("tool_history") or []
        )
        if len(options) < 2:
            return False

        raw_content = str(
            (state.get("model_response") or {}).get("content") or ""
        ).strip()
        try:
            parsed = json.loads(raw_content)
        except JSONDecodeError:
            parsed = None

        answer = (
            parsed.get("answer")
            if isinstance(parsed, dict)
            else raw_content
        )
        if not isinstance(answer, str):
            return False

        normalized_answer = answer.strip()
        mentioned_options = sum(
            option in normalized_answer for option in options
        )
        return (
            normalized_answer.endswith(("?", "؟"))
            and mentioned_options >= 2
        )

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
    def _get_pending_interrupts(snapshot) -> list[Any]:
        return [
            pending_interrupt
            for task in snapshot.tasks
            for pending_interrupt in task.interrupts
        ]

    @classmethod
    def _serialize_pending_snapshot(cls, snapshot) -> dict[str, Any]:
        pending_interrupts = cls._get_pending_interrupts(snapshot)
        if not pending_interrupts:
            raise ValueError("The graph has no pending clarification.")

        current_interrupt = pending_interrupts[0]
        values = snapshot.values or {}
        return {
            "success": True,
            "status": "clarification_required",
            "answer": None,
            "clarification": getattr(
                current_interrupt,
                "value",
                current_interrupt,
            ),
            "interrupt_id": getattr(current_interrupt, "id", None),
            "used_chunk_ids": [],
            "iterations": values.get("iterations", 0),
            "tool_history": values.get("tool_history", []),
            "messages": values.get("messages", []),
            "memory_message_count": len(values.get("messages", [])),
            "error": None,
        }

    @staticmethod
    def _serialize_result(
        final_state: dict[str, Any],
    ) -> dict[str, Any]:
        interrupts = final_state.get("__interrupt__") or []
        if interrupts:
            current_interrupt = interrupts[0]
            return {
                "success": True,
                "status": "clarification_required",
                "answer": None,
                "clarification": getattr(
                    current_interrupt,
                    "value",
                    current_interrupt,
                ),
                "interrupt_id": getattr(
                    current_interrupt,
                    "id",
                    None,
                ),
                "used_chunk_ids": [],
                "iterations": final_state.get("iterations", 0),
                "tool_history": final_state.get("tool_history", []),
                "messages": final_state.get("messages", []),
                "memory_message_count": len(
                    final_state.get("messages", [])
                ),
                "error": None,
            }

        return {
            "success": final_state.get(
                "success",
                False,
            ),
            "status": (
                "completed"
                if final_state.get("success")
                else "failed"
            ),
            "answer": final_state.get("answer"),
            "clarification": None,
            "interrupt_id": None,
            "used_chunk_ids": final_state.get(
                "used_chunk_ids",
                [],
            ),
            "iterations": final_state.get(
                "iterations",
                0,
            ),
            "finish_reason": final_state.get(
                "finish_reason"
            ),
            "tool_history": final_state.get(
                "tool_history",
                [],
            ),
            "messages": final_state.get(
                "messages",
                [],
            ),
            "memory_message_count": len(
                final_state.get("messages", [])
            ),
            "error": final_state.get("error"),
        }
