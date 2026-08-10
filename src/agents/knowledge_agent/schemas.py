from typing import Literal

from pydantic import BaseModel, Field


class KnowledgeAgentRequest(BaseModel):
    message: str = Field(
        ...,
        min_length=1,
        max_length=10_000,
        description=(
            "The user's question or instruction "
            "for the project knowledge agent."
        ),
        examples=[
            "ما الحد الأقصى لأيام العمل عن بُعد؟",
        ],
    )
    thread_id: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description=(
            "The thread ID for the conversation. "
            "This is used to maintain context across multiple messages."
        ),
        examples=[
            "thread-12345",
        ],
    )


class KnowledgeAgentSource(BaseModel):
    asset_id: int | None = None
    asset_name: str | None = None
    chunk_id: int | None = None
    score: float | None = None


class KnowledgeAgentResumeRequest(BaseModel):
    thread_id: str = Field(..., min_length=1, max_length=255)
    response: str = Field(..., min_length=1, max_length=10_000)


class KnowledgeAgentClarification(BaseModel):
    type: Literal["clarification"] = "clarification"
    question: str
    options: list[str] = Field(default_factory=list)


class KnowledgeAgentResponse(BaseModel):
    success: bool

    status: Literal[
        "completed",
        "clarification_required",
        "failed",
    ] = "completed"

    project_id: int

    answer: str | None = None

    iterations: int = 0

    sources: list[KnowledgeAgentSource] = Field(
        default_factory=list,
    )

    clarification: KnowledgeAgentClarification | None = None

    interrupt_id: str | None = None

    memory_message_count: int = 0

    error: str | None = None


class KnowledgeAgentMemoryResponse(BaseModel):
    success: bool
    project_id: int
    thread_id: str
    exists: bool
    message_count: int = 0
    pending_clarification: bool = False
    cleared: bool = False
    confirmation_required: bool = False
    error: str | None = None


class KnowledgeAgentFinalOutput(BaseModel):
    answer: str

    used_chunk_ids: list[int] = Field(
        default_factory=list,
    )
