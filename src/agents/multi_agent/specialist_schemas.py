from enum import Enum

from pydantic import BaseModel, Field, model_validator


class SpecialistAction(str, Enum):
    ANSWER = "answer"
    HANDOFF = "handoff"
    CLARIFICATION = "clarification"


class HandoffReason(str, Enum):
    PROJECT_KNOWLEDGE = "project_knowledge"
    EXTERNAL_INFORMATION = "external_information"
    ACTION_REQUIRED = "action_required"
    OUTSIDE_SPECIALIST_SCOPE = "outside_specialist_scope"


class SpecialistResponse(BaseModel):
    action: SpecialistAction
    answer: str | None = Field(default=None, min_length=1)
    handoff_reason: HandoffReason | None = None
    question: str | None = Field(default=None, min_length=1)
    options: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def validate_action_contract(self) -> "SpecialistResponse":
        if self.answer is not None:
            self.answer = self.answer.strip()
            if not self.answer:
                raise ValueError("answer cannot be blank.")

        if self.question is not None:
            self.question = self.question.strip()
            if not self.question:
                raise ValueError("question cannot be blank.")

        normalized_options: list[str] = []
        for option in self.options:
            normalized_option = option.strip()
            if not normalized_option:
                raise ValueError("clarification options cannot be blank.")
            if normalized_option not in normalized_options:
                normalized_options.append(normalized_option)
        self.options = normalized_options

        if self.action == SpecialistAction.ANSWER:
            if self.answer is None:
                raise ValueError("An answer action requires answer.")
            if self.handoff_reason is not None:
                raise ValueError(
                    "An answer action cannot contain handoff_reason."
                )
            if self.question is not None or self.options:
                raise ValueError(
                    "An answer action cannot contain clarification fields."
                )
            return self

        if self.action == SpecialistAction.HANDOFF:
            if self.handoff_reason is None:
                raise ValueError("A handoff action requires handoff_reason.")
            if self.answer is not None:
                raise ValueError("A handoff action cannot contain answer.")
            if self.question is not None or self.options:
                raise ValueError(
                    "A handoff action cannot contain clarification fields."
                )
            return self

        if self.question is None:
            raise ValueError(
                "A clarification action requires question."
            )
        if self.answer is not None or self.handoff_reason is not None:
            raise ValueError(
                "A clarification action cannot answer or hand off."
            )
        return self
