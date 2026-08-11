import asyncio
import json
from json import JSONDecodeError
from typing import Any

from agents.tools import (
    GetCurrentTimeTool,
    GetCurrentWeatherTool,
    OpenMeteoClient,
    ToolRegistry,
)

from .handoff import build_handoff_update
from .specialist_parser import (
    SpecialistResponseParseError,
    SpecialistResponseParser,
)
from .specialist_hitl import (
    ClarificationIdFactory,
    SpecialistResumeError,
    build_specialist_clarification_update,
    get_specialist_resume_message,
)
from .specialist_schemas import SpecialistAction
from .state import AgentName, MultiAgentState, TaskStatus
from .utility_prompts import build_utility_agent_system_prompt


def build_utility_tool_registry(
    *,
    open_meteo_client: OpenMeteoClient | None = None,
) -> ToolRegistry:
    client = open_meteo_client or OpenMeteoClient()
    registry = ToolRegistry()
    registry.register_tool(GetCurrentTimeTool(client))
    registry.register_tool(GetCurrentWeatherTool(client))
    return registry


class UtilityAgent:
    def __init__(
        self,
        *,
        llm_provider,
        tool_registry: ToolRegistry | None = None,
        max_iterations: int = 4,
        max_tool_calls_per_iteration: int = 4,
        max_tokens: int = 1200,
        temperature: float = 0,
        max_memory_messages: int = 40,
        interrupt_id_factory: ClarificationIdFactory | None = None,
    ) -> None:
        if max_iterations < 1:
            raise ValueError("max_iterations must be at least 1.")
        if max_tool_calls_per_iteration < 1:
            raise ValueError(
                "max_tool_calls_per_iteration must be at least 1."
            )
        if max_memory_messages < 2:
            raise ValueError("max_memory_messages must be at least 2.")

        self._llm_provider = llm_provider
        self._tool_registry = (
            tool_registry or build_utility_tool_registry()
        )
        self._max_iterations = max_iterations
        self._max_tool_calls_per_iteration = (
            max_tool_calls_per_iteration
        )
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._max_memory_messages = max_memory_messages
        self._interrupt_id_factory = interrupt_id_factory

    async def __call__(
        self,
        state: MultiAgentState,
    ) -> dict[str, Any]:
        user_message = str(state.get("user_message") or "").strip()
        if not user_message:
            return self._failure("user_message cannot be blank.")

        return await self._run(state, user_message=user_message)

    async def resume(
        self,
        state: MultiAgentState,
    ) -> dict[str, Any]:
        try:
            response = get_specialist_resume_message(
                state,
                target_agent=AgentName.UTILITY,
            )
        except SpecialistResumeError as exc:
            return self._failure(str(exc))

        return await self._run(state, user_message=response)

    async def _run(
        self,
        state: MultiAgentState,
        *,
        user_message: str,
    ) -> dict[str, Any]:

        canonical_history = self._normalize_history(
            state.get("messages") or []
        )
        raw_tool_history = state.get("tool_history") or []
        if not isinstance(raw_tool_history, list):
            return self._failure("tool_history must be a list.")
        tool_history = list(raw_tool_history)

        try:
            provider_messages = self._build_provider_messages(
                canonical_history,
                user_message,
            )
        except Exception:
            return self._failure(
                "Failed to build utility agent messages."
            )

        for iteration in range(1, self._max_iterations + 1):
            try:
                model_response = await asyncio.to_thread(
                    self._llm_provider.generate_tool_response,
                    messages=provider_messages,
                    tools=self._tool_registry.get_schemas(),
                    tool_choice="auto",
                    max_tokens=self._max_tokens,
                    temperature=self._temperature,
                )
            except Exception:
                return self._failure(
                    "Failed to call the utility agent LLM."
                )

            if not isinstance(model_response, dict):
                return self._failure(
                    "The utility agent returned an invalid response."
                )

            tool_calls = model_response.get("tool_calls") or []
            if tool_calls:
                if not isinstance(tool_calls, list):
                    return self._failure(
                        "The utility agent returned invalid tool calls."
                    )
                if len(tool_calls) > self._max_tool_calls_per_iteration:
                    return self._failure(
                        "The utility agent requested too many tools."
                    )

                try:
                    provider_messages.append(
                        self._llm_provider
                        .construct_assistant_tool_message(model_response)
                    )
                except Exception:
                    return self._failure(
                        "Failed to construct the utility tool message."
                    )

                for tool_call in tool_calls:
                    execution = await self._execute_tool_call(tool_call)
                    tool_history.append(execution)
                    try:
                        provider_messages.append(
                            self._llm_provider
                            .construct_tool_result_message(
                                tool_call_id=execution["tool_call_id"],
                                tool_name=execution["tool_name"],
                                result=execution["result"],
                            )
                        )
                    except Exception:
                        return self._failure(
                            "Failed to construct the utility tool result."
                        )
                continue

            try:
                response = SpecialistResponseParser.parse(
                    model_response.get("content")
                )
            except SpecialistResponseParseError:
                return self._failure(
                    "The utility agent returned an invalid response."
                )

            if response.action == SpecialistAction.HANDOFF:
                update = build_handoff_update(
                    state,
                    from_agent=AgentName.UTILITY,
                    reason=response.handoff_reason,
                )
                update["tool_history"] = tool_history
                return update

            if response.action == SpecialistAction.CLARIFICATION:
                try:
                    update = build_specialist_clarification_update(
                        state,
                        from_agent=AgentName.UTILITY,
                        input_message=user_message,
                        question=response.question,
                        options=response.options,
                        max_memory_messages=self._max_memory_messages,
                        interrupt_id_factory=self._interrupt_id_factory,
                    )
                except ValueError:
                    return self._failure(
                        "The utility agent returned invalid clarification."
                    )
                update["tool_history"] = tool_history
                update["final_response"]["iterations"] = iteration
                return update

            return self._success(
                canonical_history=canonical_history,
                tool_history=tool_history,
                user_message=user_message,
                answer=response.answer,
                iterations=iteration,
            )

        return self._failure(
            "The utility agent exceeded the iteration limit."
        )

    async def _execute_tool_call(
        self,
        tool_call: Any,
    ) -> dict[str, Any]:
        if not isinstance(tool_call, dict):
            return self._invalid_tool_execution()

        tool_call_id = str(tool_call.get("id") or "")
        tool_name = str(tool_call.get("name") or "")
        try:
            arguments = self._parse_arguments(
                tool_call.get("arguments")
            )
        except ValueError:
            return self._invalid_tool_execution(
                tool_call_id=tool_call_id,
                tool_name=tool_name,
            )

        try:
            result = await self._tool_registry.execute(
                name=tool_name,
                arguments=arguments,
            )
        except KeyError:
            result = {
                "success": False,
                "tool_name": tool_name,
                "result": None,
                "error": "Unknown utility tool.",
            }

        return {
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
            "arguments": arguments,
            "result": result,
        }

    def _build_provider_messages(
        self,
        canonical_history: list[dict[str, str]],
        user_message: str,
    ) -> list[dict[str, Any]]:
        role_map = {
            "user": self._llm_provider.enums.USER.value,
            "assistant": self._llm_provider.enums.ASSISTANT.value,
        }
        messages = [
            self._llm_provider.construct_prompt(
                prompt=build_utility_agent_system_prompt(),
                role=self._llm_provider.enums.SYSTEM.value,
            )
        ]
        for message in canonical_history:
            messages.append(
                self._llm_provider.construct_prompt(
                    prompt=message["content"],
                    role=role_map[message["role"]],
                )
            )
        messages.append(
            self._llm_provider.construct_prompt(
                prompt=user_message,
                role=self._llm_provider.enums.USER.value,
            )
        )
        return messages

    def _success(
        self,
        *,
        canonical_history: list[dict[str, str]],
        tool_history: list[dict[str, Any]],
        user_message: str,
        answer: str,
        iterations: int,
    ) -> dict[str, Any]:
        retained_limit = self._max_memory_messages - 2
        retained_history = (
            canonical_history[-retained_limit:]
            if retained_limit
            else []
        )
        while (
            retained_history
            and retained_history[0]["role"] != "user"
        ):
            retained_history.pop(0)

        messages = [
            *retained_history,
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": answer},
        ]
        return {
            "messages": messages,
            "tool_history": tool_history,
            "active_agent": AgentName.UTILITY.value,
            "resume_target": None,
            "task_status": TaskStatus.COMPLETED.value,
            "pending_interrupt": None,
            "pending_user_message": None,
            "handoff_reason": None,
            "final_response": {
                "success": True,
                "status": TaskStatus.COMPLETED.value,
                "agent": AgentName.UTILITY.value,
                "answer": answer,
                "iterations": iterations,
            },
            "error": None,
        }

    @staticmethod
    def _parse_arguments(raw_arguments: Any) -> dict[str, Any]:
        if isinstance(raw_arguments, dict):
            return raw_arguments
        if not isinstance(raw_arguments, str):
            raise ValueError("Tool arguments must be an object.")
        try:
            parsed = json.loads(raw_arguments)
        except JSONDecodeError as exc:
            raise ValueError("Tool arguments contain invalid JSON.") from exc
        if not isinstance(parsed, dict):
            raise ValueError("Tool arguments must be an object.")
        return parsed

    @staticmethod
    def _normalize_history(
        messages: list[dict[str, Any]],
    ) -> list[dict[str, str]]:
        normalized: list[dict[str, str]] = []
        for message in messages:
            if not isinstance(message, dict):
                continue
            role = message.get("role")
            content = str(message.get("content") or "").strip()
            if role not in {"user", "assistant"} or not content:
                continue
            normalized.append({"role": role, "content": content})
        return normalized

    @staticmethod
    def _invalid_tool_execution(
        *,
        tool_call_id: str = "",
        tool_name: str = "",
    ) -> dict[str, Any]:
        return {
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
            "arguments": {},
            "result": {
                "success": False,
                "tool_name": tool_name,
                "result": None,
                "error": "Invalid utility tool call.",
            },
        }

    @staticmethod
    def _failure(message: str) -> dict[str, Any]:
        return {
            "active_agent": AgentName.UTILITY.value,
            "resume_target": None,
            "task_status": TaskStatus.FAILED.value,
            "pending_interrupt": None,
            "pending_user_message": None,
            "final_response": None,
            "error": message,
        }
