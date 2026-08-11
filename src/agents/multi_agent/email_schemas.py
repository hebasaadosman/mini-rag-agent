from email.utils import parseaddr
from enum import Enum

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from .specialist_schemas import HandoffReason


class EmailModelAction(str, Enum):
    DRAFT = "draft"
    CLARIFICATION = "clarification"
    HANDOFF = "handoff"


class EmailApprovalDecision(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"


class EmailDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    to: str = Field(min_length=3, max_length=320)
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=100_000)

    @field_validator("to")
    @classmethod
    def validate_recipient(cls, value: str) -> str:
        normalized = value.strip()
        if any(character in normalized for character in "\r\n"):
            raise ValueError("Email recipient cannot contain new lines.")

        display_name, address = parseaddr(normalized)
        if display_name or address != normalized:
            raise ValueError("A single plain email address is required.")
        local_part, separator, domain = address.rpartition("@")
        if (
            separator != "@"
            or not local_part
            or "." not in domain
            or domain.startswith(".")
            or domain.endswith(".")
        ):
            raise ValueError("The email recipient is invalid.")
        return normalized

    @field_validator("subject")
    @classmethod
    def validate_subject(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized or any(
            character in normalized for character in "\r\n"
        ):
            raise ValueError("Email subject is invalid.")
        return normalized

    @field_validator("body")
    @classmethod
    def validate_body(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Email body cannot be blank.")
        return normalized


class EmailModelResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: EmailModelAction
    draft: EmailDraft | None = None
    question: str | None = Field(default=None, min_length=1)
    options: list[str] = Field(default_factory=list, max_length=20)
    handoff_reason: HandoffReason | None = None

    @model_validator(mode="after")
    def validate_action_contract(self) -> "EmailModelResponse":
        if self.question is not None:
            self.question = self.question.strip()
            if not self.question:
                raise ValueError("question cannot be blank.")

        normalized_options: list[str] = []
        for option in self.options:
            normalized = option.strip()
            if not normalized:
                raise ValueError("options cannot contain blank values.")
            if normalized not in normalized_options:
                normalized_options.append(normalized)
        self.options = normalized_options

        if self.action == EmailModelAction.DRAFT:
            if self.draft is None:
                raise ValueError("A draft action requires draft.")
            if (
                self.question is not None
                or self.options
                or self.handoff_reason is not None
            ):
                raise ValueError("A draft action contains invalid fields.")
            return self

        if self.action == EmailModelAction.CLARIFICATION:
            if self.question is None:
                raise ValueError(
                    "A clarification action requires question."
                )
            if self.draft is not None or self.handoff_reason is not None:
                raise ValueError(
                    "A clarification action contains invalid fields."
                )
            return self

        if self.handoff_reason is None:
            raise ValueError("A handoff action requires handoff_reason.")
        if self.draft is not None or self.question is not None or self.options:
            raise ValueError("A handoff action contains invalid fields.")
        return self
