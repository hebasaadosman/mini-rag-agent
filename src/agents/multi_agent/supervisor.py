import asyncio
from typing import Any

from .decision_parser import (
    SupervisorDecisionParseError,
    SupervisorDecisionParser,
)
from .prompts import build_supervisor_system_prompt
from .schemas import SupervisorDecision
from .specialist_schemas import HandoffReason
from .state import AgentName, MultiAgentState, TaskStatus
from .supervisor_hitl import (
    SupervisorResumeError,
    get_supervisor_resume_message,
)


class SupervisorAgent:
    def __init__(
        self,
        *,
        llm_provider,
        max_tokens: int = 300,
        temperature: float = 0,
    ) -> None:
        self._llm_provider = llm_provider
        self._max_tokens = max_tokens
        self._temperature = temperature

    async def __call__(
        self,
        state: MultiAgentState,
    ) -> dict[str, Any]:
        user_message = str(state.get("user_message") or "").strip()
        if not user_message:
            return self._failure("user_message cannot be blank.")

        try:
            system_message = self._llm_provider.construct_prompt(
                prompt=self._build_system_prompt(state),
                role=self._llm_provider.enums.SYSTEM.value,
            )
            content = await asyncio.to_thread(
                self._llm_provider.generate_text,
                user_message,
                chat_history=[system_message],
                max_tokens=self._max_tokens,
                temperature=self._temperature,
            )
        except Exception:
            return self._failure("Failed to call the supervisor LLM.")

        try:
            decision = SupervisorDecisionParser.parse(
                {"content": content}
            )
        except SupervisorDecisionParseError:
            return self._failure(
                "The supervisor returned an invalid routing decision."
            )

        if self._selects_visited_specialist(decision, state):
            try:
                retry_system_message = self._llm_provider.construct_prompt(
                    prompt=(
                        f"{self._build_system_prompt(state)}\n\n"
                        "Your previous decision selected a specialist that "
                        "is unavailable for this routing attempt. Re-evaluate "
                        "the request once. Select an untried specialist or "
                        "ask a routing clarification."
                    ),
                    role=self._llm_provider.enums.SYSTEM.value,
                )
                retry_content = await asyncio.to_thread(
                    self._llm_provider.generate_text,
                    user_message,
                    chat_history=[retry_system_message],
                    max_tokens=self._max_tokens,
                    temperature=self._temperature,
                )
                decision = SupervisorDecisionParser.parse(
                    {"content": retry_content}
                )
            except Exception:
                return self._failure(
                    "Failed to repair the supervisor routing decision."
                )

            if self._selects_visited_specialist(decision, state):
                return self._failure(
                    "The supervisor repeatedly selected an unavailable "
                    "specialist."
                )

        return {
            "supervisor_decision": decision.model_dump(mode="json"),
            "active_agent": AgentName.SUPERVISOR.value,
            "task_status": TaskStatus.RUNNING.value,
            "error": None,
        }

    async def resume(
        self,
        state: MultiAgentState,
    ) -> dict[str, Any]:
        try:
            response = get_supervisor_resume_message(state)
        except SupervisorResumeError as exc:
            return self._failure(str(exc))

        original_request = str(state.get("user_message") or "").strip()
        if not original_request:
            return self._failure("The original routing request is missing.")

        resumed_state = {
            **state,
            "handoff_count": 0,
            "handoff_reason": None,
            "visited_agents": [],
            "user_message": (
                f"Original request:\n{original_request}\n\n"
                f"Clarification response:\n{response}"
            ),
        }
        update = await self(resumed_state)
        if update.get("error"):
            return update
        return {
            **update,
            "resume_target": None,
            "pending_interrupt": None,
            "pending_user_message": None,
            "handoff_count": 0,
            "handoff_reason": None,
            "visited_agents": [],
        }

    @staticmethod
    def _selects_visited_specialist(
        decision: SupervisorDecision,
        state: MultiAgentState,
    ) -> bool:
        target = {
            "knowledge": AgentName.KNOWLEDGE,
            "utility": AgentName.UTILITY,
            "general": AgentName.GENERAL,
            "email": AgentName.EMAIL,
        }.get(decision.route.value)
        if target is None:
            return False

        raw_visited = state.get("visited_agents") or []
        if not isinstance(raw_visited, list):
            return False
        try:
            visited = {AgentName(agent) for agent in raw_visited}
        except (TypeError, ValueError):
            return False
        return target in visited

    @staticmethod
    def _build_system_prompt(state: MultiAgentState) -> str:
        prompt = build_supervisor_system_prompt()
        raw_reason = state.get("handoff_reason")
        raw_visited_agents = state.get("visited_agents") or []
        if raw_reason is None or not isinstance(raw_visited_agents, list):
            return prompt

        try:
            reason = HandoffReason(raw_reason)
            visited_agents = [
                AgentName(agent)
                for agent in raw_visited_agents
            ]
        except (TypeError, ValueError):
            return prompt

        if not visited_agents:
            return prompt

        tried_agents = ", ".join(
            agent.value for agent in visited_agents
        )
        return (
            f"{prompt}\n\n"
            "Trusted orchestration metadata:\n"
            f"- Handoff reason: {reason.value}\n"
            f"- Specialists already tried: {tried_agents}\n"
            "Do not select a specialist already tried during this turn."
        )

    @staticmethod
    def _failure(message: str) -> dict[str, Any]:
        return {
            "supervisor_decision": None,
            "active_agent": AgentName.SUPERVISOR.value,
            "task_status": TaskStatus.FAILED.value,
            "error": message,
        }
