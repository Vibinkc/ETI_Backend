"""Dashboard statistics API router."""

import re
from datetime import date, datetime, timedelta
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.mongodb import mongodb_settings
from app.core.timeutils import utcnow
from app.models.document import Document, DocumentChunk
from app.models.document_query_hit import DocumentQueryHit
from app.models.form_submission import FormSubmission

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _parse_range(start: str | None, end: str | None) -> tuple[datetime, datetime] | None:
    """Turn YYYY-MM-DD query params into an inclusive datetime range.

    Returns None when either bound is missing or unparseable, so the caller
    falls back to its preset period rather than erroring. The end date is
    pushed to the end of that day so a single-day range covers the whole day.
    """
    if not start or not end:
        return None
    try:
        start_dt = datetime.strptime(start, "%Y-%m-%d")
        end_dt = datetime.strptime(end, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
    except (ValueError, TypeError):
        logger.warning(f"Ignoring unparseable date range: start={start!r} end={end!r}")
        return None

    if start_dt > end_dt:
        start_dt, end_dt = (
            end_dt.replace(hour=0, minute=0, second=0),
            start_dt.replace(hour=23, minute=59, second=59),
        )
    return start_dt, end_dt


def _window_for(
    period: str | None, start: str | None, end: str | None
) -> tuple[tuple[datetime, datetime], tuple[datetime, datetime], str] | None:
    """Resolve the dashboard filter into (window, previous_window, label).

    Returns None when no filter is supplied, so callers keep their all-time
    behaviour. The previous window is the same length immediately before, which
    is what makes the change figure meaningful for an arbitrary range.
    """
    custom = _parse_range(start, end)
    if custom:
        win_start, win_end = custom
        label = "previous period"
    elif period in ("day", "week", "month"):
        win_end = utcnow()
        span = {"day": 1, "week": 7, "month": 30}[period]
        win_start = win_end - timedelta(days=span)
        label = {"day": "yesterday", "week": "last week", "month": "last month"}[period]
    else:
        return None

    window_span = win_end - win_start
    return (win_start, win_end), (win_start - window_span, win_start), label


async def _count_window(
    db: AsyncSession, conversations_collection: Any, win: tuple[datetime, datetime]
) -> tuple[int, int, int, int]:
    """Documents, queries, sessions and submissions inside one window."""
    w_start, w_end = win

    documents = (
        await db.scalar(
            select(func.count(Document.id)).where(
                and_(Document.created_at >= w_start, Document.created_at <= w_end)
            )
        )
        or 0
    )

    submissions = (
        await db.scalar(
            select(func.count(FormSubmission.id)).where(
                and_(FormSubmission.created_at >= w_start, FormSubmission.created_at <= w_end)
            )
        )
        or 0
    )

    convs = await conversations_collection.find({"created_at": {"$gte": w_start, "$lte": w_end}}).to_list(
        length=None
    )

    sessions = len({c.get("session_id") for c in convs if c.get("session_id")})
    queries = sum(len([m for m in c.get("messages", []) if m.get("role") == "user"]) for c in convs)
    return documents, queries, sessions, submissions


async def _windowed_stats(
    db: AsyncSession, window: tuple[datetime, datetime], previous: tuple[datetime, datetime], label: str
) -> dict[str, Any]:
    """Counters scoped to the dashboard filter, compared with the prior window."""
    try:
        conversations_collection = mongodb_settings.get_database()["conversations"]
        cur = await _count_window(db, conversations_collection, window)
        prev = await _count_window(db, conversations_collection, previous)

        def pct(current: int, before: int) -> str:
            if before == 0:
                return "+100%" if current > 0 else "0%"
            change = ((current - before) / before) * 100
            return f"{'+' if change >= 0 else ''}{change:.0f}%"

        def absolute(current: int, before: int) -> str:
            change = current - before
            return f"{'+' if change >= 0 else ''}{change}"

        return {
            "documents_processed": cur[0],
            "documents_change": pct(cur[0], prev[0]),
            "ai_queries": cur[1],
            "ai_queries_change": pct(cur[1], prev[1]),
            "active_sessions": cur[2],
            "active_sessions_change": absolute(cur[2], prev[2]),
            "form_submissions": cur[3],
            "form_submissions_change": absolute(cur[3], prev[3]),
            "comparison_label": label,
        }
    except Exception as e:
        logger.error(f"Error getting windowed stats: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting stats: {e!s}") from e


def _granularity_for(period: str | None, span_days: int | None = None) -> str:
    """Bucket size for a preset, or one inferred from a custom range's length."""
    if span_days is not None:
        if span_days <= 31:
            return "day"
        if span_days <= 180:
            return "week"
        return "month"
    return period if period in ("day", "week", "month") else "day"


def _bucket_start(value: datetime | date, granularity: str) -> date:
    """Snap a date to the start of its day, ISO week, or calendar month."""
    d = value.date() if isinstance(value, datetime) else value
    if granularity == "month":
        return d.replace(day=1)
    if granularity == "week":
        return d - timedelta(days=d.weekday())
    return d


def _bucket_label(d: date, granularity: str) -> str:
    """Axis label for a bucket start date.

    Spelled out rather than abbreviated: "w/c" is a convention not everyone
    reads, whereas "Week of Aug 17" needs no explanation.
    """
    if granularity == "month":
        return d.strftime("%b %Y")
    if granularity == "week":
        return f"Week of {d.strftime('%b %d')}"
    return d.strftime("%b %d")


def parse_user_agent(user_agent: str | None) -> dict[str, str]:
    """Parse user agent string to extract device and browser info."""
    if not user_agent:
        return {"device": "Unknown", "browser": "Unknown", "platform": "Unknown"}

    device = "Desktop"
    browser = "Unknown"
    platform = "Unknown"

    # Detect mobile devices
    mobile_pattern = r"(Mobile|Android|iPhone|iPad|iPod|BlackBerry|Windows Phone)"
    if re.search(mobile_pattern, user_agent, re.IGNORECASE):
        if "iPad" in user_agent or ("Android" in user_agent and "Mobile" not in user_agent):
            device = "Tablet"
        else:
            device = "Mobile"

    # Detect browsers
    if "Chrome" in user_agent and "Edg" not in user_agent:
        browser = "Chrome"
    elif "Firefox" in user_agent:
        browser = "Firefox"
    elif "Safari" in user_agent and "Chrome" not in user_agent:
        browser = "Safari"
    elif "Edg" in user_agent:
        browser = "Edge"
    elif "Opera" in user_agent or "OPR" in user_agent:
        browser = "Opera"

    # Detect platform
    if "Windows" in user_agent:
        platform = "Windows"
    elif "Mac" in user_agent or "Macintosh" in user_agent:
        platform = "macOS"
    elif "Linux" in user_agent:
        platform = "Linux"
    elif "Android" in user_agent:
        platform = "Android"
    elif "iOS" in user_agent or "iPhone" in user_agent or "iPad" in user_agent:
        platform = "iOS"

    return {"device": device, "browser": browser, "platform": platform}


@router.get("/stats/today")
async def get_today_stats(
    db: AsyncSession = Depends(get_db),
    period: str | None = Query(None, regex="^(day|week|month)$"),
    start: str | None = Query(None),
    end: str | None = Query(None),
) -> dict[str, Any]:
    """Headline counters.

    With no filter these are all-time totals compared against yesterday. When
    the dashboard filter is applied the counters are scoped to that window and
    compared against the preceding window of equal length.
    """
    window = _window_for(period, start, end)
    if window:
        return await _windowed_stats(db, *window)
    try:
        today = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        # Total documents uploaded (all time)
        result = await db.execute(select(func.count(Document.id)))
        documents_total = result.scalar() or 0

        # Documents uploaded today (all documents, not just processed)
        result = await db.execute(select(func.count(Document.id)).where(Document.created_at >= today))
        documents_processed = result.scalar() or 0

        # Form submissions today
        result = await db.execute(
            select(func.count(FormSubmission.id)).where(FormSubmission.created_at >= today)
        )
        form_submissions = result.scalar() or 0

        # Get conversations from MongoDB
        db_mongo = mongodb_settings.get_database()
        conversations_collection = db_mongo["conversations"]

        # Active sessions today (unique session_ids)
        today_conversations = await conversations_collection.find({"created_at": {"$gte": today}}).to_list(
            length=None
        )

        active_sessions = len(
            {conv.get("session_id") for conv in today_conversations if conv.get("session_id")}
        )

        # AI queries today (count user messages)
        ai_queries = 0
        for conv in today_conversations:
            messages = conv.get("messages", [])
            user_messages = [msg for msg in messages if msg.get("role") == "user"]
            ai_queries += len(user_messages)

        # Calculate changes from yesterday
        yesterday = today - timedelta(days=1)

        # Documents yesterday (all documents, not just processed)
        result = await db.execute(
            select(func.count(Document.id)).where(
                and_(Document.created_at >= yesterday, Document.created_at < today)
            )
        )
        documents_yesterday = result.scalar() or 0

        # Form submissions yesterday
        result = await db.execute(
            select(func.count(FormSubmission.id)).where(
                and_(FormSubmission.created_at >= yesterday, FormSubmission.created_at < today)
            )
        )
        submissions_yesterday = result.scalar() or 0

        # Sessions yesterday
        yesterday_conversations = await conversations_collection.find(
            {"created_at": {"$gte": yesterday, "$lt": today}}
        ).to_list(length=None)
        sessions_yesterday = len(
            {conv.get("session_id") for conv in yesterday_conversations if conv.get("session_id")}
        )

        # Queries yesterday
        queries_yesterday = 0
        for conv in yesterday_conversations:
            messages = conv.get("messages", [])
            user_messages = [msg for msg in messages if msg.get("role") == "user"]
            queries_yesterday += len(user_messages)

        # Calculate percentage changes
        def calc_change(current: int, previous: int) -> str:
            if previous == 0:
                return "+100%" if current > 0 else "0%"
            change = ((current - previous) / previous) * 100
            sign = "+" if change >= 0 else ""
            return f"{sign}{change:.0f}%"

        def calc_change_absolute(current: int, previous: int) -> str:
            change = current - previous
            sign = "+" if change >= 0 else ""
            return f"{sign}{abs(change)}"

        # Get total counts for all metrics
        # Total form submissions
        result = await db.execute(select(func.count(FormSubmission.id)))
        form_submissions_total = result.scalar() or 0

        # Total conversations
        all_conversations = await conversations_collection.find({}).to_list(length=None)
        total_sessions = len({conv.get("session_id") for conv in all_conversations if conv.get("session_id")})

        # Total AI queries (all user messages)
        total_queries = 0
        for conv in all_conversations:
            messages = conv.get("messages", [])
            user_messages = [msg for msg in messages if msg.get("role") == "user"]
            total_queries += len(user_messages)

        return {
            "documents_processed": documents_total,  # Show total instead of today's
            "documents_change": calc_change(documents_processed, documents_yesterday),
            "ai_queries": total_queries,  # Show total instead of today's
            "ai_queries_change": calc_change(ai_queries, queries_yesterday),
            "active_sessions": total_sessions,  # Show total instead of today's
            "active_sessions_change": calc_change_absolute(active_sessions, sessions_yesterday),
            "form_submissions": form_submissions_total,  # Show total instead of today's
            "form_submissions_change": calc_change_absolute(form_submissions, submissions_yesterday),
        }
    except Exception as e:
        logger.error(f"Error getting today's stats: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting today's stats: {e!s}") from e


@router.get("/stats/activity")
async def get_activity_stats(
    period: str = Query("week", regex="^(day|week|month)$"),
    start: str | None = Query(None, description="Range start, YYYY-MM-DD (overrides period)"),
    end: str | None = Query(None, description="Range end, YYYY-MM-DD (overrides period)"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get activity statistics (questions vs documents) over time.

    A start/end pair overrides the preset period so the dashboard can offer a
    custom date range.
    """
    try:
        db_mongo = mongodb_settings.get_database()
        conversations_collection = db_mongo["conversations"]

        # Date range and bucket size both follow the selected period, so
        # "Months" aggregates by calendar month rather than relabelling days.
        end_date = utcnow()
        if period == "day":
            start_date = end_date - timedelta(days=7)
        elif period == "week":
            start_date = end_date - timedelta(weeks=8)
        else:  # month
            start_date = end_date - timedelta(days=182)  # ~6 months
        granularity = _granularity_for(period)

        custom = _parse_range(start, end)
        if custom:
            start_date, end_date = custom
            granularity = _granularity_for(None, (end_date - start_date).days)

        # Get documents by day (all uploaded documents, not just processed)
        result = await db.execute(
            select(func.date(Document.created_at).label("date"), func.count(Document.id).label("count"))
            .where(and_(Document.created_at >= start_date, Document.created_at <= end_date))
            .group_by(func.date(Document.created_at))
            .order_by(func.date(Document.created_at))
        )
        documents_by_date: dict[date, int] = {}
        for row in result.all():
            key = _bucket_start(row.date, granularity)
            # row.count is the SQL count() alias; mypy sees tuple.count instead.
            documents_by_date[key] = documents_by_date.get(key, 0) + cast("int", row.count)

        # Get conversations and count user messages by day
        conversations = await conversations_collection.find(
            {"created_at": {"$gte": start_date, "$lte": end_date}}
        ).to_list(length=None)

        questions_by_date = {}
        for conv in conversations:
            created_at = conv.get("created_at")
            if not created_at:
                continue

            # Handle different date formats from MongoDB
            if isinstance(created_at, str):
                try:
                    created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                except Exception:  # nosec B112 - skip rows with an unparseable timestamp
                    continue
            elif not isinstance(created_at, datetime):
                continue

            date_key = _bucket_start(created_at, granularity)
            messages = conv.get("messages", [])
            user_messages = [msg for msg in messages if msg.get("role") == "user"]

            if date_key not in questions_by_date:
                questions_by_date[date_key] = 0
            questions_by_date[date_key] += len(user_messages)

        # Combine and format data
        all_dates = set(documents_by_date.keys()) | set(questions_by_date.keys())
        data = []

        for bucket_date in sorted(all_dates):
            label = _bucket_label(bucket_date, granularity)

            data.append(
                {
                    "day" if period == "day" else "date": label,
                    "questions": questions_by_date.get(bucket_date, 0),
                    "documents": documents_by_date.get(bucket_date, 0),
                }
            )

        return {"data": data}
    except Exception as e:
        logger.error(f"Error getting activity stats: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting activity stats: {e!s}") from e


@router.get("/stats/visitors")
async def get_visitor_stats(
    period: str = Query("month", regex="^(day|week|month|year)$"),
    start: str | None = Query(None, description="Range start, YYYY-MM-DD (overrides period)"),
    end: str | None = Query(None, description="Range end, YYYY-MM-DD (overrides period)"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get visitor insights over time.

    A start/end pair overrides the preset period.
    """
    try:
        db_mongo = mongodb_settings.get_database()
        conversations_collection = db_mongo["conversations"]

        # Determine date range
        end_date = utcnow()
        if period == "day":
            start_date = end_date - timedelta(days=30)  # Last 30 days
        elif period == "week":
            start_date = end_date - timedelta(weeks=8)
        elif period == "month":
            start_date = end_date - timedelta(days=180)  # 6 months
        else:  # year
            start_date = end_date - timedelta(days=365)

        custom = _parse_range(start, end)
        if custom:
            start_date, end_date = custom

        # Get conversations
        conversations = await conversations_collection.find(
            {"created_at": {"$gte": start_date, "$lte": end_date}}
        ).to_list(length=None)

        # Bucket size follows the preset: days, ISO weeks, or calendar months.
        granularity = _granularity_for(period if period != "year" else "month")
        custom_span = _parse_range(start, end)
        if custom_span:
            granularity = _granularity_for(None, (custom_span[1] - custom_span[0]).days)

        if granularity in ("day", "week"):
            conversations_by_period = {}
            sessions_by_period: dict[str, set[str]] = {}
            submissions_by_period = {}

            for conv in conversations:
                created_at = conv.get("created_at")
                if not created_at:
                    continue

                # Handle different date formats from MongoDB
                if isinstance(created_at, str):
                    try:
                        created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    except Exception:  # nosec B112 - skip rows with an unparseable timestamp
                        continue
                elif not isinstance(created_at, datetime):
                    continue

                day_key = _bucket_start(created_at, granularity).strftime("%Y-%m-%d")
                session_id = conv.get("session_id")

                if day_key not in conversations_by_period:
                    conversations_by_period[day_key] = 0
                    sessions_by_period[day_key] = set()
                    submissions_by_period[day_key] = 0

                conversations_by_period[day_key] += 1
                if session_id:
                    sessions_by_period[day_key].add(session_id)

            # Get form submissions by day
            day_expr = func.date_trunc("day", FormSubmission.created_at)
            result = await db.execute(
                select(
                    func.to_char(day_expr, "YYYY-MM-DD").label("day"),
                    func.count(FormSubmission.id).label("count"),
                )
                .where(FormSubmission.created_at >= start_date)
                .group_by(day_expr)
                .order_by(day_expr)
            )

            for row in result.all():
                # row.count is the SQL count() alias; mypy sees tuple.count instead.
                submissions_by_period[row.day] = cast("int", row.count)

            # Format data for days
            data = []
            for day_key in sorted(conversations_by_period.keys()):
                day_date = datetime.strptime(day_key, "%Y-%m-%d")
                data.append(
                    {
                        "day": _bucket_label(day_date.date(), granularity),
                        "conversations": conversations_by_period[day_key],
                        "sessions": len(sessions_by_period.get(day_key, set())),
                        "submissions": submissions_by_period.get(day_key, 0),
                    }
                )
        else:
            # Aggregate by month (existing logic)
            conversations_by_period = {}
            sessions_by_period = {}
            submissions_by_period = {}

            for conv in conversations:
                created_at = conv.get("created_at")
                if not created_at:
                    continue

                # Handle different date formats from MongoDB
                if isinstance(created_at, str):
                    try:
                        created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    except Exception:  # nosec B112 - skip rows with an unparseable timestamp
                        continue
                elif not isinstance(created_at, datetime):
                    continue

                month_key = created_at.strftime("%Y-%m")
                session_id = conv.get("session_id")

                if month_key not in conversations_by_period:
                    conversations_by_period[month_key] = 0
                    sessions_by_period[month_key] = set()
                    submissions_by_period[month_key] = 0

                conversations_by_period[month_key] += 1
                if session_id:
                    sessions_by_period[month_key].add(session_id)

            # Get form submissions by month
            month_expr = func.date_trunc("month", FormSubmission.created_at)
            result = await db.execute(
                select(
                    func.to_char(month_expr, "YYYY-MM").label("month"),
                    func.count(FormSubmission.id).label("count"),
                )
                .where(FormSubmission.created_at >= start_date)
                .group_by(month_expr)
                .order_by(month_expr)
            )

            for row in result.all():
                # row.count is the SQL count() alias; mypy sees tuple.count instead.
                submissions_by_period[row.month] = cast("int", row.count)

            # Format data for months
            data = []
            for month_key in sorted(conversations_by_period.keys()):
                month_date = datetime.strptime(month_key, "%Y-%m")
                data.append(
                    {
                        "month": month_date.strftime("%b"),
                        "conversations": conversations_by_period[month_key],
                        "sessions": len(sessions_by_period.get(month_key, set())),
                        "submissions": submissions_by_period.get(month_key, 0),
                    }
                )

        return {"data": data}
    except Exception as e:
        logger.error(f"Error getting visitor stats: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting visitor stats: {e!s}") from e


@router.get("/stats/top-documents")
async def get_top_documents(
    limit: int = Query(10, ge=1, le=50),
    period: str | None = Query(None, regex="^(day|week|month)$"),
    start: str | None = Query(None),
    end: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Top documents by chunk count, optionally scoped to the dashboard filter.

    Scoping is by upload date - nothing records when a document was used to
    answer a question, so "top in this period" means "added in this period".
    """
    window = _window_for(period, start, end)
    try:
        # For now, return documents by chunk count (as proxy for usage)
        # In future, could track actual query usage
        result = await db.execute(
            select(
                Document.id,
                Document.name,
                Document.created_at,
                func.count(DocumentChunk.id).label("chunk_count"),
            )
            .join(DocumentChunk, Document.id == DocumentChunk.document_id)
            .where(
                and_(  # type: ignore[arg-type]  # and_() types as ColumnElement[bool] | bool
                    Document.created_at >= window[0][0], Document.created_at <= window[0][1]
                )
                if window
                else True
            )
            .group_by(Document.id)
            .order_by(func.count(DocumentChunk.id).desc())
            .limit(limit)
        )

        documents = []
        for row in result.all():
            documents.append(
                {
                    "id": row.id,
                    "name": row.name,
                    "chunk_count": row.chunk_count,
                    "created_at": row.created_at.isoformat(),
                }
            )

        return {"data": documents}
    except Exception as e:
        logger.error(f"Error getting top documents: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting top documents: {e!s}") from e


@router.get("/stats/document-importance")
async def get_document_importance(
    limit: int = Query(10, ge=1, le=20),
    period: str | None = Query(None, regex="^(day|week|month)$"),
    start: str | None = Query(None),
    end: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Documents ranked by how many queries they actually answered.

    Counts rows in document_query_hit, which the chat and assistant endpoints
    write whenever a document supplies context. Scoping is by *hit* time, so
    "this week" means questions asked this week, not documents uploaded then.
    """
    window = _window_for(period, start, end)
    try:
        hit_filter: list[Any] = [DocumentQueryHit.id.isnot(None)]
        if window:
            hit_filter = [
                DocumentQueryHit.created_at >= window[0][0],
                DocumentQueryHit.created_at <= window[0][1],
            ]

        result = await db.execute(
            select(
                Document.id,
                Document.name,
                Document.file_size,
                Document.created_at,
                func.count(DocumentQueryHit.id).label("query_count"),
            )
            .outerjoin(DocumentQueryHit, and_(DocumentQueryHit.document_id == Document.id, *hit_filter))
            .group_by(Document.id)
        )
        rows = result.all()

        # Chunk counts come from a separate aggregate so the join above cannot
        # multiply hit rows by chunk rows.
        chunk_rows = await db.execute(
            select(DocumentChunk.document_id, func.count(DocumentChunk.id)).group_by(
                DocumentChunk.document_id
            )
        )
        chunks_by_doc = {doc_id: n for doc_id, n in chunk_rows.all()}  # noqa: C416

        max_queries = max((r.query_count or 0) for r in rows) if rows else 0

        documents = [
            {
                "id": r.id,
                "name": r.name,
                "chunk_count": chunks_by_doc.get(r.id, 0),
                "file_size": r.file_size or 0,
                "usage_count": r.query_count or 0,
                # Share of the busiest document, so the leader reads 100%
                "importance_score": (
                    min(100, round((r.query_count or 0) / max_queries * 100, 1)) if max_queries > 0 else 0
                ),
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]

        documents.sort(key=lambda d: d["usage_count"], reverse=True)
        return {"data": documents[:limit], "total_queries": sum(d["usage_count"] for d in documents)}
    except Exception as e:
        logger.error(f"Error getting document importance: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting document importance: {e!s}") from e


@router.get("/stats/top-websites")
async def get_top_websites(
    limit: int = Query(10, ge=1, le=50), db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    """Get top websites by conversation count."""
    try:
        db_mongo = mongodb_settings.get_database()
        conversations_collection = db_mongo["conversations"]

        # Aggregate conversations by website_url
        conversations = await conversations_collection.find({}).to_list(length=None)

        website_stats: dict[str, dict[str, Any]] = {}
        for conv in conversations:
            website_url = conv.get("website_url") or "Unknown"
            if website_url not in website_stats:
                website_stats[website_url] = {"conversations": 0, "sessions": set(), "submissions": 0}

            website_stats[website_url]["conversations"] += 1
            session_id = conv.get("session_id")
            if session_id:
                website_stats[website_url]["sessions"].add(session_id)

        # Get form submissions by website
        result = await db.execute(
            select(FormSubmission.website_url, func.count(FormSubmission.id).label("count")).group_by(
                FormSubmission.website_url
            )
        )

        for row in result.all():
            website_url = row.website_url or "Unknown"
            if website_url in website_stats:
                website_stats[website_url]["submissions"] = row.count

        # Format and sort
        websites = []
        for website_url, stats in website_stats.items():
            websites.append(
                {
                    "website_url": website_url,
                    "conversations": stats["conversations"],
                    "sessions": len(stats["sessions"]),
                    "submissions": stats["submissions"],
                }
            )

        websites.sort(key=lambda x: x["conversations"], reverse=True)
        return {"data": websites[:limit]}
    except Exception as e:
        logger.error(f"Error getting top websites: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting top websites: {e!s}") from e


@router.get("/stats/devices")
async def get_device_stats(
    db: AsyncSession = Depends(get_db),  # noqa: ARG001  # FastAPI dependency, part of route signature
) -> dict[str, Any]:
    """Get device and browser statistics."""
    try:
        db_mongo = mongodb_settings.get_database()
        conversations_collection = db_mongo["conversations"]

        conversations = await conversations_collection.find({}).to_list(length=None)

        device_counts: dict[str, int] = {}
        browser_counts: dict[str, int] = {}
        platform_counts: dict[str, int] = {}
        total = 0

        for conv in conversations:
            user_agent = conv.get("user_agent")
            parsed = parse_user_agent(user_agent)

            device = parsed["device"]
            browser = parsed["browser"]
            platform = parsed["platform"]

            device_counts[device] = device_counts.get(device, 0) + 1
            browser_counts[browser] = browser_counts.get(browser, 0) + 1
            platform_counts[platform] = platform_counts.get(platform, 0) + 1
            total += 1

        # Format device data
        device_data: list[dict[str, Any]] = []
        for device, count in device_counts.items():
            device_data.append(
                {
                    "device": device,
                    "count": count,
                    "percentage": round((count / total * 100) if total > 0 else 0, 1),
                }
            )
        device_data.sort(key=lambda x: x["count"], reverse=True)

        # Format browser data
        browser_data: list[dict[str, Any]] = []
        for browser, count in browser_counts.items():
            browser_data.append(
                {
                    "browser": browser,
                    "count": count,
                    "percentage": round((count / total * 100) if total > 0 else 0, 1),
                }
            )
        browser_data.sort(key=lambda x: x["count"], reverse=True)

        return {"devices": device_data, "browsers": browser_data, "total": total}
    except Exception as e:
        logger.error(f"Error getting device stats: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting device stats: {e!s}") from e


@router.get("/stats/user-activity")
async def get_user_activity_stats(
    period: str = Query("month", regex="^(week|month|year)$"), db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    """Get user activity statistics over time."""
    try:
        db_mongo = mongodb_settings.get_database()
        conversations_collection = db_mongo["conversations"]

        # Determine date range
        end_date = utcnow()
        if period == "week":
            start_date = end_date - timedelta(weeks=8)
        elif period == "month":
            start_date = end_date - timedelta(days=180)  # 6 months
        else:  # year
            start_date = end_date - timedelta(days=365)

        # Get conversations
        conversations = await conversations_collection.find({"created_at": {"$gte": start_date}}).to_list(
            length=None
        )

        # Aggregate by month
        conversations_by_month = {}
        documents_by_month = {}
        submissions_by_month = {}
        sessions_by_month: dict[str, set[str]] = {}

        for conv in conversations:
            created_at = conv.get("created_at")
            if not created_at:
                continue

            # Handle different date formats from MongoDB
            if isinstance(created_at, str):
                try:
                    created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                except Exception:  # nosec B112 - skip rows with an unparseable timestamp
                    continue
            elif not isinstance(created_at, datetime):
                continue

            month_key = created_at.strftime("%Y-%m")
            session_id = conv.get("session_id")

            if month_key not in conversations_by_month:
                conversations_by_month[month_key] = 0
                sessions_by_month[month_key] = set()

            conversations_by_month[month_key] += 1
            if session_id:
                sessions_by_month[month_key].add(session_id)

        # Get documents by month
        # Use date_trunc for proper month grouping in PostgreSQL
        doc_month_expr = func.date_trunc("month", Document.created_at)
        result = await db.execute(
            select(
                func.to_char(doc_month_expr, "YYYY-MM").label("month"), func.count(Document.id).label("count")
            )
            .where(Document.created_at >= start_date)
            .group_by(doc_month_expr)
            .order_by(doc_month_expr)
        )

        for row in result.all():
            documents_by_month[row.month] = row.count

        # Get form submissions by month
        # Use date_trunc for proper month grouping in PostgreSQL
        form_month_expr = func.date_trunc("month", FormSubmission.created_at)
        result = await db.execute(
            select(
                func.to_char(form_month_expr, "YYYY-MM").label("month"),
                func.count(FormSubmission.id).label("count"),
            )
            .where(FormSubmission.created_at >= start_date)
            .group_by(form_month_expr)
            .order_by(form_month_expr)
        )

        for row in result.all():
            submissions_by_month[row.month] = row.count

        # Format data
        data = []
        all_months = (
            set(conversations_by_month.keys())
            | set(documents_by_month.keys())
            | set(submissions_by_month.keys())
        )

        for month_key in sorted(all_months):
            month_date = datetime.strptime(month_key, "%Y-%m")
            data.append(
                {
                    "month": month_date.strftime("%b"),
                    "conversations": conversations_by_month.get(month_key, 0),
                    "documents": documents_by_month.get(month_key, 0),
                    "submissions": submissions_by_month.get(month_key, 0),
                    "sessions": len(sessions_by_month.get(month_key, set())),
                }
            )

        return {"data": data}
    except Exception as e:
        logger.error(f"Error getting user activity stats: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting user activity stats: {e!s}") from e
