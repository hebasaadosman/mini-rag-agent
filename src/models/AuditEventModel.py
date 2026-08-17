"""PostgreSQL persistence adapter for append-only audit events."""

from typing import Mapping

from .BaseDataModel import BaseDataModel
from .db_schemes import AuditEvent


class AuditEventModel(BaseDataModel):
    @classmethod
    async def create_instance(cls, db_client: object):
        return cls(db_client)

    async def create_event(
        self,
        *,
        principal_id: str,
        action: str,
        outcome: str,
        project_id: int | None,
        metadata: Mapping[str, str] | None,
    ) -> AuditEvent:
        async with self.db_client() as session:
            async with session.begin():
                event = AuditEvent(
                    principal_id=principal_id,
                    action=action,
                    outcome=outcome,
                    project_id=project_id,
                    metadata_json=dict(metadata) if metadata else None,
                )
                session.add(event)
            await session.refresh(event)
            return event
