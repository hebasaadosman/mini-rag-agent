"""Persistence boundary for audit events."""

from __future__ import annotations

from typing import Protocol

from auditing.audit_event import AuditEvent
from models.AuditEventModel import AuditEventModel


class AuditLogger(Protocol):
    async def record(self, event: AuditEvent) -> None: ...


class DatabaseAuditLogger:
    """Append-only audit writer backed by the application's PostgreSQL store."""

    def __init__(self, audit_event_model: AuditEventModel) -> None:
        self._audit_event_model = audit_event_model

    async def record(self, event: AuditEvent) -> None:
        await self._audit_event_model.create_event(
            principal_id=event.principal_id,
            action=event.action.value,
            outcome=event.outcome.value,
            project_id=event.project_id,
            metadata=event.metadata,
        )
