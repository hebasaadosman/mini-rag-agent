"""Persistence and ownership enforcement for private conversation threads."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .BaseDataModel import BaseDataModel
from .db_schemes import ConversationThread, ProjectMembership


class ConversationThreadAccessDenied(PermissionError):
    """Raised without revealing whether a private thread exists."""


@dataclass(frozen=True, slots=True)
class ConversationThreadAccess:
    project_id: int
    thread_id: str
    owner_principal_id: str
    checkpoint_key: str


class ConversationThreadModel(BaseDataModel):
    """Claim and resolve private threads under an existing project membership."""

    @classmethod
    async def create_instance(cls, db_client: object):
        return cls(db_client)

    async def claim_or_require_owner(
        self,
        *,
        project_id: int,
        thread_id: str,
        principal_id: str,
    ) -> ConversationThreadAccess:
        """Atomically create a private thread or require its existing owner."""
        normalized_thread_id = self._normalize_thread_id(thread_id)
        async with self.db_client() as session:
            for attempt in range(2):
                try:
                    # A row that already exists is serialized by FOR UPDATE.
                    # When it does not exist, the database unique constraint is
                    # the final arbiter.  If another transaction wins that
                    # insert race, retry once in a fresh transaction and read
                    # the established owner.
                    async with session.begin():
                        await self._require_current_membership(
                            session=session,
                            project_id=project_id,
                            principal_id=principal_id,
                        )
                        result = await session.execute(
                            select(ConversationThread)
                            .where(
                                ConversationThread.project_id == project_id,
                                ConversationThread.thread_id
                                == normalized_thread_id,
                            )
                            .with_for_update()
                        )
                        thread = result.scalar_one_or_none()
                        if thread is None:
                            thread = ConversationThread(
                                project_id=project_id,
                                thread_id=normalized_thread_id,
                                owner_principal_id=principal_id,
                                scope="private",
                            )
                            session.add(thread)
                            await session.flush()
                        self._require_owner(thread, principal_id)
                        return self._access_from(thread)
                except IntegrityError as exc:
                    if attempt == 0:
                        continue
                    # The conflict may be for the public thread ownership row
                    # or the opaque checkpoint key.  Do not reveal which.
                    raise ConversationThreadAccessDenied(
                        "The conversation cannot be accessed."
                    ) from exc

        raise ConversationThreadAccessDenied("The conversation cannot be accessed.")

    async def require_owner(
        self,
        *,
        project_id: int,
        thread_id: str,
        principal_id: str,
    ) -> ConversationThreadAccess:
        """Require both a live project membership and private-thread ownership."""
        normalized_thread_id = self._normalize_thread_id(thread_id)
        async with self.db_client() as session:
            await self._require_current_membership(
                session=session,
                project_id=project_id,
                principal_id=principal_id,
            )
            result = await session.execute(
                select(ConversationThread).where(
                    ConversationThread.project_id == project_id,
                    ConversationThread.thread_id == normalized_thread_id,
                )
            )
            thread = result.scalar_one_or_none()
            self._require_owner(thread, principal_id)
            return self._access_from(thread)

    @staticmethod
    async def _require_current_membership(
        *, session, project_id: int, principal_id: str
    ) -> None:
        result = await session.execute(
            select(ProjectMembership.membership_id).where(
                ProjectMembership.project_id == project_id,
                ProjectMembership.principal_id == principal_id,
            )
        )
        if result.scalar_one_or_none() is None:
            # This deliberately does not inherit the project-level
            # platform_admin bypass. Private-thread administration is an
            # explicit unresolved policy, so the safe default is deny.
            raise ConversationThreadAccessDenied(
                "The conversation cannot be accessed."
            )

    @staticmethod
    def _require_owner(
        thread: ConversationThread | None, principal_id: str) -> None:
        if (
            thread is None
            or thread.scope != "private"
            or thread.owner_principal_id != principal_id
        ):
            raise ConversationThreadAccessDenied(
                "The conversation cannot be accessed."
            )

    @staticmethod
    def _access_from(thread: ConversationThread) -> ConversationThreadAccess:
        return ConversationThreadAccess(
            project_id=thread.project_id,
            thread_id=thread.thread_id,
            owner_principal_id=thread.owner_principal_id,
            checkpoint_key=thread.checkpoint_key,
        )

    @staticmethod
    def _normalize_thread_id(thread_id: str) -> str:
        value = str(thread_id or "").strip()
        if not value or len(value) > 255:
            raise ConversationThreadAccessDenied(
                "The conversation cannot be accessed."
            )
        return value
