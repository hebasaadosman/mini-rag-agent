import asyncio
from hashlib import sha256
from typing import Any
from uuid import uuid4

from agents.tools import SendEmailTool

from .email_hitl import (
    EmailApprovalStateError,
    build_email_approval_update,
    get_pending_email_approval,
    parse_email_approval_decision,
)
from .email_parser import EmailResponseParseError, EmailResponseParser
from .email_prompts import build_email_agent_system_prompt
from .email_schemas import EmailApprovalDecision, EmailModelAction
from .handoff import build_handoff_update
from .specialist_hitl import (
    ClarificationIdFactory,
    SpecialistResumeError,
    build_specialist_clarification_update,
    get_specialist_resume_message,
)
from .state import AgentName, MultiAgentState, TaskStatus


class EmailAgent:
    def __init__(
        self,
        *,
        llm_provider,
        send_email_tool: SendEmailTool,
        max_tokens: int = 1500,
        temperature: float = 0,
        max_memory_messages: int = 40,
        interrupt_id_factory: ClarificationIdFactory | None = None,
    ) -> None:
        if not isinstance(send_email_tool, SendEmailTool):
            raise TypeError("send_email_tool must be a SendEmailTool.")
        if max_memory_messages < 2:
            raise ValueError("max_memory_messages must be at least 2.")

        self._llm_provider = llm_provider
        self._send_email_tool = send_email_tool
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._max_memory_messages = max_memory_messages
        self._interrupt_id_factory = (
            interrupt_id_factory or (lambda: uuid4().hex)
        )

    async def __call__(
        self,
        state: MultiAgentState,
    ) -> dict[str, Any]:
        user_message = str(state.get("user_message") or "").strip()
        if not user_message:
            return self._failure("user_message cannot be blank.")
        return await self._create_draft(
            state,
            user_message=user_message,
        )

    async def resume(
        self,
        state: MultiAgentState,
    ) -> dict[str, Any]:
        try:
            response = get_specialist_resume_message(
                state,
                target_agent=AgentName.EMAIL,
            )
        except SpecialistResumeError as exc:
            return self._failure(str(exc))

        pending = state.get("pending_interrupt") or {}
        if pending.get("type") == "email_approval":
            return await self._resume_approval(
                state,
                response=response,
            )
        if pending.get("type") == "clarification":
            return await self._create_draft(
                state,
                user_message=response,
            )
        return self._failure("The email pending action is invalid.")

    async def _create_draft(
        self,
        state: MultiAgentState,
        *,
        user_message: str,
    ) -> dict[str, Any]:
        canonical_history = self._normalize_history(
            state.get("messages")
        )
        try:
            content = await asyncio.to_thread(
                self._llm_provider.generate_text,
                user_message,
                chat_history=self._build_provider_history(
                    canonical_history
                ),
                max_tokens=self._max_tokens,
                temperature=self._temperature,
            )
        except Exception:
            return self._failure("Failed to call the email agent LLM.")

        try:
            response = EmailResponseParser.parse(content)
        except EmailResponseParseError:
            return self._failure(
                "The email agent returned an invalid response."
            )

        if response.action == EmailModelAction.HANDOFF:
            return build_handoff_update(
                state,
                from_agent=AgentName.EMAIL,
                reason=response.handoff_reason,
            )
        if response.action == EmailModelAction.CLARIFICATION:
            try:
                return build_specialist_clarification_update(
                    state,
                    from_agent=AgentName.EMAIL,
                    input_message=user_message,
                    question=response.question,
                    options=response.options,
                    max_memory_messages=self._max_memory_messages,
                    interrupt_id_factory=self._interrupt_id_factory,
                )
            except ValueError:
                return self._failure(
                    "The email agent returned invalid clarification."
                )

        try:
            return build_email_approval_update(
                state,
                draft=response.draft,
                input_message=user_message,
                max_memory_messages=self._max_memory_messages,
                interrupt_id_factory=self._interrupt_id_factory,
            )
        except ValueError:
            return self._failure(
                "The email agent returned an invalid draft."
            )

    async def _resume_approval(
        self,
        state: MultiAgentState,
        *,
        response: str,
    ) -> dict[str, Any]:
        try:
            draft, interrupt_id = get_pending_email_approval(state)
        except EmailApprovalStateError as exc:
            return self._failure(str(exc))

        decision = parse_email_approval_decision(response)
        if decision is None:
            return build_email_approval_update(
                state,
                draft=draft,
                input_message=response,
                max_memory_messages=self._max_memory_messages,
                interrupt_id_factory=self._interrupt_id_factory,
            )
        if decision == EmailApprovalDecision.REJECT:
            return self._cancelled_update(
                state,
                response=response,
                draft=draft.model_dump(mode="json"),
            )

        raw_tool_history = state.get("tool_history") or []
        if not isinstance(raw_tool_history, list):
            return self._failure("tool_history must be a list.")

        audit_arguments = {
            "recipient": draft.to,
            "subject": draft.subject,
            "body_sha256": sha256(draft.body.encode("utf-8")).hexdigest(),
            "idempotency_key": interrupt_id,
        }
        try:
            delivery = await self._send_email_tool.execute(
                recipient=draft.to,
                subject=draft.subject,
                body=draft.body,
                idempotency_key=interrupt_id,
            )
        except Exception:
            tool_history = [
                *raw_tool_history,
                {
                    "tool_name": self._send_email_tool.name,
                    "arguments": audit_arguments,
                    "execution_result": {
                        "success": False,
                        "result": None,
                        "error": "Email delivery failed.",
                    },
                },
            ]
            failure = self._failure("Failed to send the approved email.")
            failure["tool_history"] = tool_history
            return failure

        if not isinstance(delivery, dict) or not delivery.get("message_id"):
            return self._failure(
                "The email delivery tool returned an invalid result."
            )

        tool_history = [
            *raw_tool_history,
            {
                "tool_name": self._send_email_tool.name,
                "arguments": audit_arguments,
                "execution_result": {
                    "success": True,
                    "result": delivery,
                    "error": None,
                },
            },
        ]
        answer = "Email sent successfully."
        return {
            "messages": self._append_conversation_turn(
                state,
                user_content=response,
                assistant_content=answer,
            ),
            "tool_history": tool_history,
            "active_agent": AgentName.EMAIL.value,
            "resume_target": None,
            "task_status": TaskStatus.COMPLETED.value,
            "pending_interrupt": None,
            "pending_user_message": None,
            "handoff_reason": None,
            "final_response": {
                "success": True,
                "status": "completed",
                "agent": AgentName.EMAIL.value,
                "answer": answer,
                "message_id": str(delivery["message_id"]),
                "recipient": draft.to,
                "replayed": bool(delivery.get("replayed")),
                "error": None,
            },
            "error": None,
        }

    def _cancelled_update(
        self,
        state: MultiAgentState,
        *,
        response: str,
        draft: dict[str, Any],
    ) -> dict[str, Any]:
        answer = "Email sending was cancelled."
        return {
            "messages": self._append_conversation_turn(
                state,
                user_content=response,
                assistant_content=answer,
            ),
            "active_agent": AgentName.EMAIL.value,
            "resume_target": None,
            "task_status": TaskStatus.CANCELLED.value,
            "pending_interrupt": None,
            "pending_user_message": None,
            "handoff_reason": None,
            "final_response": {
                "success": True,
                "status": "cancelled",
                "agent": AgentName.EMAIL.value,
                "answer": answer,
                "draft": draft,
                "error": None,
            },
            "error": None,
        }

    def _build_provider_history(
        self,
        canonical_history: list[dict[str, str]],
    ) -> list[dict[str, Any]]:
        role_map = {
            "user": self._llm_provider.enums.USER.value,
            "assistant": self._llm_provider.enums.ASSISTANT.value,
        }
        history = [
            self._llm_provider.construct_prompt(
                prompt=build_email_agent_system_prompt(),
                role=self._llm_provider.enums.SYSTEM.value,
            )
        ]
        for message in canonical_history:
            history.append(
                self._llm_provider.construct_prompt(
                    prompt=message["content"],
                    role=role_map[message["role"]],
                )
            )
        return history

    def _append_conversation_turn(
        self,
        state: MultiAgentState,
        *,
        user_content: str,
        assistant_content: str,
    ) -> list[dict[str, str]]:
        history = self._normalize_history(state.get("messages"))
        retained_limit = self._max_memory_messages - 2
        retained = history[-retained_limit:] if retained_limit else []
        while retained and retained[0]["role"] != "user":
            retained.pop(0)
        return [
            *retained,
            {"role": "user", "content": user_content},
            {"role": "assistant", "content": assistant_content},
        ]

    @staticmethod
    def _normalize_history(raw_messages: Any) -> list[dict[str, str]]:
        if not isinstance(raw_messages, list):
            return []
        normalized: list[dict[str, str]] = []
        for message in raw_messages:
            if not isinstance(message, dict):
                continue
            role = message.get("role")
            content = str(message.get("content") or "").strip()
            if role in {"user", "assistant"} and content:
                normalized.append({"role": role, "content": content})
        return normalized

    @staticmethod
    def _failure(message: str) -> dict[str, Any]:
        return {
            "active_agent": AgentName.EMAIL.value,
            "resume_target": None,
            "task_status": TaskStatus.FAILED.value,
            "pending_interrupt": None,
            "pending_user_message": None,
            "final_response": None,
            "error": message,
        }
