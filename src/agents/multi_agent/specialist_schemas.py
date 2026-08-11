from enum import Enum

from pydantic import BaseModel, Field, model_validator


class SpecialistAction(str, Enum):
    ANSWER = "answer"
    HANDOFF = "handoff"


class HandoffReason(str, Enum):
    PROJECT_KNOWLEDGE = "project_knowledge"
    EXTERNAL_INFORMATION = "external_information"
    ACTION_REQUIRED = "action_required"
    OUTSIDE_SPECIALIST_SCOPE = "outside_specialist_scope"


class SpecialistResponse(BaseModel):
    action: SpecialistAction
    answer: str | None = Field(default=None, min_length=1)
    handoff_reason: HandoffReason | None = None

    @model_validator(mode="after")
    def validate_action_contract(self) -> "SpecialistResponse":
        if self.answer is not None:
            self.answer = self.answer.strip()
            if not self.answer:
                raise ValueError("answer cannot be blank.")

        if self.action == SpecialistAction.ANSWER:
            if self.answer is None:
                raise ValueError("An answer action requires answer.")
            if self.handoff_reason is not None:
                raise ValueError(
                    "An answer action cannot contain handoff_reason."
                )
            return self

        if self.handoff_reason is None:
            raise ValueError("A handoff action requires handoff_reason.")
        if self.answer is not None:
            raise ValueError("A handoff action cannot contain answer.")
        return self
