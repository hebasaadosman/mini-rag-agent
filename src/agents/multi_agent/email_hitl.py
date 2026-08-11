from typing import Any

from pydantic import ValidationError

from .email_schemas import EmailApprovalDecision, EmailDraft
from .specialist_hitl import ClarificationIdFactory
from .state import AgentName, MultiAgentState, TaskStatus


class EmailApprovalStateError(ValueError):
    pass


_APPROVE_ALIASES = {
    "approve",
    "send",
    "yes",
    "موافق",
    "نعم",
    "إرسال",
    "ارسال",
    "أرسل",
    "ارسل",
}
_REJECT_ALIASES = {
    "reject",
    "cancel",
    "no",
    "رفض",
    "لا",
    "إلغاء",
    "الغاء",
}


def build_email_approval_update(
    state: MultiAgentState,
    *,
    draft: EmailDraft,
    input_message: str,
    max_memory_messages: int = 40,
    interrupt_id_factory: ClarificationIdFactory,
) -> dict[str, Any]:
    if max_memory_messages < 2:
        raise ValueError("max_memory_messages must be at least 2.")
    normalized_input = str(input_message or "").strip()
    if not normalized_input:
        raise ValueError("input_message cannot be blank.")

    draft_payload = draft.model_dump(mode="json")
    interrupt_id = _resolve_approval_id(
        state,
        draft_payload=draft_payload,
        interrupt_id_factory=interrupt_id_factory,
    )
    preview = _draft_preview(draft)
    messages = _append_conversation_turn(
        state.get("messages"),
        user_content=normalized_input,
        assistant_content=preview,
        max_memory_messages=max_memory_messages,
    )
    approval = {
        "type": "email_approval",
        "question": "Send this exact email draft?",
        "options": ["approve", "reject"],
        "interrupt_id": interrupt_id,
        "draft": draft_payload,
    }
    return {
        "messages": messages,
        "active_agent": AgentName.EMAIL.value,
        "resume_target": AgentName.EMAIL.value,
        "task_status": TaskStatus.WAITING_FOR_USER.value,
        "pending_interrupt": approval,
        "pending_user_message": None,
        "handoff_reason": None,
        "final_response": {
            "success": True,
            "status": "approval_required",
            "agent": AgentName.EMAIL.value,
            "answer": None,
            "approval": {
                key: value
                for key, value in approval.items()
                if key != "draft"
            },
            "draft": draft_payload,
            "error": None,
        },
        "error": None,
    }


def get_pending_email_approval(
    state: MultiAgentState,
) -> tuple[EmailDraft, str]:
    try:
        task_status = TaskStatus(state.get("task_status"))
        resume_target = AgentName(state.get("resume_target"))
    except (TypeError, ValueError) as exc:
        raise EmailApprovalStateError(
            "No email approval is pending."
        ) from exc

    pending = state.get("pending_interrupt")
    if (
        task_status != TaskStatus.WAITING_FOR_USER
        or resume_target != AgentName.EMAIL
        or not isinstance(pending, dict)
        or pending.get("type") != "email_approval"
    ):
        raise EmailApprovalStateError("No email approval is pending.")

    interrupt_id = str(pending.get("interrupt_id") or "").strip()
    if not interrupt_id:
        raise EmailApprovalStateError(
            "The pending email approval has no interrupt ID."
        )
    try:
        draft = EmailDraft.model_validate(pending.get("draft"))
    except ValidationError:
        raise EmailApprovalStateError(
            "The pending email draft is invalid."
        ) from None
    return draft, interrupt_id


def parse_email_approval_decision(
    response: str,
) -> EmailApprovalDecision | None:
    if not isinstance(response, str):
        return None
    normalized = response.strip().casefold()
    if normalized in {value.casefold() for value in _APPROVE_ALIASES}:
        return EmailApprovalDecision.APPROVE
    if normalized in {value.casefold() for value in _REJECT_ALIASES}:
        return EmailApprovalDecision.REJECT
    return None


def _resolve_approval_id(
    state: MultiAgentState,
    *,
    draft_payload: dict[str, Any],
    interrupt_id_factory: ClarificationIdFactory,
) -> str:
    pending = state.get("pending_interrupt")
    if (
        isinstance(pending, dict)
        and pending.get("type") == "email_approval"
        and pending.get("draft") == draft_payload
    ):
        existing_id = str(pending.get("interrupt_id") or "").strip()
        if existing_id:
            return existing_id

    interrupt_id = str(interrupt_id_factory() or "").strip()
    if not interrupt_id:
        raise ValueError("interrupt_id_factory returned a blank ID.")
    return interrupt_id


def _draft_preview(draft: EmailDraft) -> str:
    return (
        f"Email draft\nTo: {draft.to}\nSubject: {draft.subject}\n\n"
        f"{draft.body}\n\nApprove or reject sending this exact draft."
    )


def _append_conversation_turn(
    raw_messages: Any,
    *,
    user_content: str,
    assistant_content: str,
    max_memory_messages: int,
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    if isinstance(raw_messages, list):
        for message in raw_messages:
            if not isinstance(message, dict):
                continue
            role = message.get("role")
            content = str(message.get("content") or "").strip()
            if role in {"user", "assistant"} and content:
                messages.append({"role": role, "content": content})

    retained_limit = max_memory_messages - 2
    retained = messages[-retained_limit:] if retained_limit else []
    while retained and retained[0]["role"] != "user":
        retained.pop(0)
    return [
        *retained,
        {"role": "user", "content": user_content},
        {"role": "assistant", "content": assistant_content},
    ]
