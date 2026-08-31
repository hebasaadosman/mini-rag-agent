"""Safe removal of expired *demo* project memberships only."""
from __future__ import annotations

import asyncio
import json

from sqlalchemy import delete, select
from redis import asyncio as redis_asyncio

from celery_app import celery_app, get_db_utils
from authentication.session_url import resolve_auth_session_redis_url
from helpers.config import get_settings
from models.db_schemes import ProjectMembership


@celery_app.task(name="tasks.demo_cleanup.cleanup_expired_demo_memberships")
def cleanup_expired_demo_memberships() -> int:
    return asyncio.run(_cleanup())


async def _cleanup() -> int:
    """Delete only `demo:` principals whose opaque BFF session no longer exists."""
    settings = get_settings()
    redis = redis_asyncio.from_url(resolve_auth_session_redis_url(settings), decode_responses=True)
    live_subjects: set[str] = set()
    try:
        async for key in redis.scan_iter(match="mini-rag:auth:session:*"):
            payload = await redis.get(key)
            if not payload:
                continue
            try:
                session = json.loads(payload)
            except json.JSONDecodeError:
                continue
            subject = session.get("subject")
            if session.get("kind") == "demo" and isinstance(subject, str):
                live_subjects.add(subject)
    finally:
        await redis.aclose()

    engine, sessions = await get_db_utils()
    try:
        async with sessions() as session:
            stale = list((await session.scalars(
                select(ProjectMembership.principal_id).where(
                    ProjectMembership.principal_id.like("demo:%")
                )
            )).all())
            stale = [principal for principal in stale if principal not in live_subjects]
            if stale:
                await session.execute(
                    delete(ProjectMembership).where(ProjectMembership.principal_id.in_(stale))
                )
                await session.commit()
            return len(stale)
    finally:
        await engine.dispose()
