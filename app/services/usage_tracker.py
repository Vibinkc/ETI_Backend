"""Record which documents supplied context for a query."""

from collections.abc import Iterable
from datetime import datetime
from typing import Any

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document_query_hit import DocumentQueryHit

# Retrieval always returns its top matches, falling back to a 0.01 threshold so
# the bot has *something* to work with. Crediting every one of those would mean
# an unrelated document gets a "query answered" every time it happens to place
# in the top five. Only chunks that clear a genuine similarity bar count.
MIN_HIT_SIMILARITY = 0.2


def documents_above_threshold(
    scored_chunks: Iterable[tuple[Any, float | None]], threshold: float = MIN_HIT_SIMILARITY
) -> set[int]:
    """Document ids whose best matching chunk cleared the bar.

    scored_chunks: iterable of (chunk, similarity) as returned by the vector store.
    """
    return {
        chunk.document_id
        for chunk, similarity in scored_chunks
        if similarity is not None and similarity >= threshold
    }


async def record_document_hits(
    db: AsyncSession, document_ids: Iterable[int], session_id: str | None = None, source: str = "widget"
) -> None:
    """Write one row per distinct document that answered this query.

    Never raises - analytics must not be able to break a chat reply.
    """
    unique = {int(d) for d in document_ids if d is not None}
    if not unique:
        return
    try:
        now = datetime.utcnow()
        for doc_id in unique:
            db.add(
                DocumentQueryHit(
                    document_id=doc_id, session_id=(session_id or None), source=source, created_at=now
                )
            )
        await db.commit()
    except Exception as e:
        logger.error(f"Could not record document hits: {e}")
        try:  # noqa: SIM105  # deliberate swallow; analytics must never break a chat reply
            await db.rollback()
        except Exception:  # nosec B110 - analytics must never break a chat reply
            pass
