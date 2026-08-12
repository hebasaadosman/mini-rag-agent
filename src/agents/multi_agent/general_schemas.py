from pydantic import BaseModel, Field, model_validator

from .specialist_schemas import SpecialistAction


class GeneralSemanticReview(BaseModel):
    """Structured evidence used to validate a General Agent answer."""

    entity_types: list[str] = Field(min_length=1)
    embedded_assumptions: list[str] = Field(default_factory=list)
    relationship_valid: bool
    verdict: str
    action: SpecialistAction
    answer: str | None = None
    question: str | None = None
    options: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_result(self) -> "GeneralSemanticReview":
        self.entity_types = [
            item.strip() for item in self.entity_types if item.strip()
        ]
        self.verdict = self.verdict.strip()
        if not self.entity_types or not self.verdict:
            raise ValueError("Semantic review evidence cannot be blank.")

        if self.action == SpecialistAction.ANSWER:
            if not self.answer or not self.answer.strip():
                raise ValueError("A reviewed answer is required.")
            self.answer = self.answer.strip()
            if self.question is not None or self.options:
                raise ValueError("An answer cannot ask clarification.")
            return self

        if self.action == SpecialistAction.CLARIFICATION:
            if not self.question or not self.question.strip():
                raise ValueError("A reviewed clarification is required.")
            self.question = self.question.strip()
            if self.answer is not None:
                raise ValueError("A clarification cannot answer.")
            return self

        raise ValueError("Semantic review cannot request a handoff.")
