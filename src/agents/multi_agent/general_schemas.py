from pydantic import BaseModel, Field, model_validator

from .specialist_schemas import HandoffReason, SpecialistAction


class GeneralSemanticReview(BaseModel):
    """Structured evidence used to validate a General Agent answer."""

    entity_types: list[str] = Field(default_factory=list)
    embedded_assumptions: list[str] = Field(default_factory=list)
    relationship_valid: bool | None = None
    verdict: str
    action: SpecialistAction
    answer: str | None = None
    handoff_reason: HandoffReason | None = None
    question: str | None = None
    options: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_result(self) -> "GeneralSemanticReview":
        self.entity_types = [
            item.strip() for item in self.entity_types if item.strip()
        ]
        self.verdict = self.verdict.strip()
        if not self.verdict:
            raise ValueError("Decision review verdict cannot be blank.")

        if self.action == SpecialistAction.ANSWER:
            if not self.answer or not self.answer.strip():
                raise ValueError("A reviewed answer is required.")
            self.answer = self.answer.strip()
            if (
                self.handoff_reason is not None
                or self.question is not None
                or self.options
            ):
                raise ValueError("An answer cannot ask clarification.")
            return self

        if self.action == SpecialistAction.CLARIFICATION:
            if not self.question or not self.question.strip():
                raise ValueError("A reviewed clarification is required.")
            self.question = self.question.strip()
            if self.answer is not None or self.handoff_reason is not None:
                raise ValueError("A clarification cannot answer.")
            return self

        if self.handoff_reason is None:
            raise ValueError("A reviewed handoff requires a reason.")
        if self.answer is not None or self.question is not None or self.options:
            raise ValueError("A handoff cannot answer or ask clarification.")
        return self
