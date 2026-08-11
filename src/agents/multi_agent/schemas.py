from enum import Enum

from pydantic import (
    BaseModel,
    Field,
    field_validator,
    model_validator,
)


class SupervisorRoute(str, Enum):
    KNOWLEDGE = "knowledge"
    UTILITY = "utility"
    GENERAL = "general"
    EMAIL = "email"
    CLARIFICATION = "clarification"


class SupervisorReason(str, Enum):
    PROJECT_KNOWLEDGE = "project_knowledge"
    EXTERNAL_INFORMATION = "external_information"
    GENERAL_CONVERSATION = "general_conversation"
    ACTION_REQUIRED = "action_required"
    AMBIGUOUS_REQUEST = "ambiguous_request"


class SupervisorDecision(BaseModel):
    route: SupervisorRoute
    reason: SupervisorReason
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
    )
    clarification_question: str | None = Field(
        default=None,
        min_length=1,
        max_length=500,
    )

    @field_validator("clarification_question")
    @classmethod
    def normalize_clarification_question(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        normalized = value.strip()
        if not normalized:
            raise ValueError(
                "clarification_question cannot be blank."
            )
        return normalized

    @model_validator(mode="after")
    def validate_clarification_contract(
        self,
    ) -> "SupervisorDecision":
        expected_reason = {
            SupervisorRoute.KNOWLEDGE: (
                SupervisorReason.PROJECT_KNOWLEDGE
            ),
            SupervisorRoute.UTILITY: (
                SupervisorReason.EXTERNAL_INFORMATION
            ),
            SupervisorRoute.GENERAL: (
                SupervisorReason.GENERAL_CONVERSATION
            ),
            SupervisorRoute.EMAIL: (
                SupervisorReason.ACTION_REQUIRED
            ),
            SupervisorRoute.CLARIFICATION: (
                SupervisorReason.AMBIGUOUS_REQUEST
            ),
        }[self.route]

        if self.reason != expected_reason:
            raise ValueError(
                "The routing reason does not match the route."
            )

        is_clarification = (
            self.route == SupervisorRoute.CLARIFICATION
        )

        if is_clarification and self.clarification_question is None:
            raise ValueError(
                "A clarification route requires a question."
            )

        if not is_clarification and self.clarification_question is not None:
            raise ValueError(
                "Only a clarification route may include a question."
            )

        return self
