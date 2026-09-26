from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MultiAgentChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=10_000)
    thread_id: str = Field(..., min_length=1, max_length=255)

    @field_validator("message", "thread_id")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value cannot be blank.")
        return normalized


class MultiAgentResumeRequest(BaseModel):
    response: str = Field(..., min_length=1, max_length=10_000)
    thread_id: str = Field(..., min_length=1, max_length=255)

    @field_validator("response", "thread_id")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value cannot be blank.")
        return normalized


class MultiAgentResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    success: bool
    status: Literal[
        "completed",
        "clarification_required",
        "approval_required",
        "switch_confirmation_required",
        "cancelled",
        "rejected",
        "failed",
    ]
    project_id: int
    thread_id: str
    agent: str | None = None
    answer: str | None = None
    clarification: dict[str, Any] | None = None
    interrupt_id: str | None = None
    iterations: int | None = None
    sources: list[dict[str, Any]] = Field(default_factory=list)
    reason: str | None = None
    message_id: str | None = None
    draft: dict[str, Any] | None = None
    error: str | None = None
