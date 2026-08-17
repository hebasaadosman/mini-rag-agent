"""Semantic validation for public Multi-Agent workflow responses.

The workflow may return structurally valid dictionaries that are still
contradictory for a client.  This module validates the business contract before
the controller maps a workflow result to the public API response.
"""

from __future__ import annotations

from typing import Any


class MultiAgentOutputContractError(ValueError):
    """Raised when a workflow result violates the public response contract."""


class MultiAgentOutputValidator:
    """Reject contradictory workflow outcomes before they leave the API."""

    _FAILURE_STATUSES = frozenset({"failed", "rejected"})
    _CLARIFICATION_STATUSES = frozenset(
        {"clarification_required", "switch_confirmation_required"}
    )

    @classmethod
    def validate(cls, result: dict[str, Any]) -> None:
        """Validate semantic invariants that a schema alone cannot express."""
        status = result.get("status")
        if not isinstance(status, str):
            raise MultiAgentOutputContractError("The workflow result has no status.")

        if status == "completed":
            cls._require_success(result, status)
            cls._require_nonblank(result.get("answer"), "answer", status)
            cls._reject_error(result, status)
            cls._validate_message_id(result)
            return

        if status in cls._CLARIFICATION_STATUSES:
            cls._require_success(result, status)
            cls._require_clarification_question(result, status)
            cls._reject_error(result, status)
            return

        if status == "approval_required":
            cls._require_success(result, status)
            cls._require_email_draft(result)
            cls._reject_error(result, status)
            return

        if status == "cancelled":
            cls._require_success(result, status)
            cls._reject_error(result, status)
            return

        if status in cls._FAILURE_STATUSES:
            if result.get("success") is not False:
                raise MultiAgentOutputContractError(
                    f"A {status} response must set success to false."
                )
            cls._require_nonblank(result.get("error"), "error", status)
            if result.get("message_id") is not None:
                raise MultiAgentOutputContractError(
                    "A failed or rejected response cannot expose a message_id."
                )

    @staticmethod
    def _require_success(result: dict[str, Any], status: str) -> None:
        if result.get("success") is not True:
            raise MultiAgentOutputContractError(
                f"A {status} response must set success to true."
            )

    @staticmethod
    def _require_nonblank(value: Any, field_name: str, status: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise MultiAgentOutputContractError(
                f"A {status} response requires a non-blank {field_name}."
            )

    @staticmethod
    def _reject_error(result: dict[str, Any], status: str) -> None:
        error = result.get("error")
        if isinstance(error, str) and error.strip():
            raise MultiAgentOutputContractError(
                f"A successful {status} response cannot also contain an error."
            )

    @classmethod
    def _require_clarification_question(
        cls,
        result: dict[str, Any],
        status: str,
    ) -> None:
        clarification = result.get("clarification")
        if not isinstance(clarification, dict):
            raise MultiAgentOutputContractError(
                f"A {status} response requires clarification details."
            )
        cls._require_nonblank(clarification.get("question"), "clarification question", status)

    @staticmethod
    def _require_email_draft(result: dict[str, Any]) -> None:
        draft = result.get("draft")
        if not isinstance(draft, dict):
            raise MultiAgentOutputContractError(
                "An approval_required response requires an email draft."
            )
        for field_name in ("to", "subject", "body"):
            value = draft.get(field_name)
            if not isinstance(value, str) or not value.strip():
                raise MultiAgentOutputContractError(
                    "An approval_required response requires a complete email draft."
                )

    @staticmethod
    def _validate_message_id(result: dict[str, Any]) -> None:
        message_id = result.get("message_id")
        if message_id is not None and result.get("agent") != "email":
            raise MultiAgentOutputContractError(
                "Only the email agent may return a message_id."
            )
