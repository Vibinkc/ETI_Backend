"""Write admin actions to the audit trail."""

from fastapi import Request
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin_activity import AdminActivity


async def log_activity(
    db: AsyncSession,
    *,
    actor_email: str,
    action: str,
    user_id: int | None = None,
    entity_type: str | None = None,
    # int is accepted because every caller passes a primary key; the body
    # already coerces with str(), so widening the annotation changes nothing
    # at runtime and matches what the callers have always done.
    entity_id: str | int | None = None,
    detail: str | None = None,
    request: Request | None = None,
) -> None:
    """Record one admin action.

    Deliberately swallows its own errors: an audit write must never be able to
    fail the action it is describing. Commits immediately so the entry survives
    even if the caller later rolls back.
    """
    ip = None
    if request is not None:
        ip = request.headers.get("x-forwarded-for") or (request.client.host if request.client else None)
        if ip:
            ip = ip.split(",")[0].strip()[:64]

    try:
        db.add(
            AdminActivity(
                user_id=user_id or None,
                actor_email=actor_email,
                action=action,
                entity_type=entity_type,
                entity_id=str(entity_id) if entity_id is not None else None,
                detail=detail,
                ip_address=ip,
            )
        )
        await db.commit()
    except Exception as e:
        logger.error(f"Could not write activity log ({action}): {e}")
        try:  # noqa: SIM105  # deliberate swallow; audit write must never fail the caller
            await db.rollback()
        except Exception:  # nosec B110 - audit write must never fail the caller
            pass
