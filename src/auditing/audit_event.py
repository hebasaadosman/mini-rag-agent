"""Safe, structured audit events. Never place request content or secrets here."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping


class AuditAction(StrEnum):
    PROJECT_ACCESS = "project.access"
    PROJECT_CREATED = "project.created"
    PROJECT_MEMBER_ROLE_GRANTED = "project.member_role_granted"


class AuditOutcome(StrEnum):
    ALLOWED = "allowed"
    DENIED = "denied"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


_SAFE_METADATA_KEYS = frozenset(
    {"permission", "role", "target_principal_id", "requested_project_id"}
)


@dataclass(frozen=True, slots=True)
class AuditEvent:
    principal_id: str
    action: AuditAction
    outcome: AuditOutcome
    project_id: int | None = None
    metadata: dict[str, str] | None = None


def create_audit_event(
    *,
    principal_id: str,
    action: AuditAction,
    outcome: AuditOutcome,
    project_id: int | None = None,
    metadata: Mapping[str, str] | None = None,
) -> AuditEvent:
    """Build an event only from explicitly allowlisted metadata."""
    normalized_principal_id = principal_id.strip()
    if not normalized_principal_id:
        raise ValueError("principal_id is required for an audit event.")
    if project_id is not None and project_id < 1:
        raise ValueError("project_id must be positive when supplied.")

    normalized_metadata: dict[str, str] | None = None
    if metadata:
        unexpected_keys = set(metadata) - _SAFE_METADATA_KEYS
        if unexpected_keys:
            raise ValueError("Audit metadata contains a non-allowlisted key.")
        normalized_metadata = {}
        for key, value in metadata.items():
            if not isinstance(value, str) or not value.strip():
                raise ValueError("Audit metadata values must be non-empty strings.")
            normalized_metadata[key] = value.strip()

    return AuditEvent(
        principal_id=normalized_principal_id,
        action=action,
        outcome=outcome,
        project_id=project_id,
        metadata=normalized_metadata,
    )
