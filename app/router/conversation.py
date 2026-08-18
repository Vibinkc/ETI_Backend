"""Conversation API router for managing conversations."""

from datetime import datetime
from typing import Any

from bson import ObjectId
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.mongodb import mongodb_settings
from app.models.form_submission import FormSubmission
from app.schema.conversation import ConversationListResponse, ConversationSchema, MessageSchema

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.get("/list")
async def list_user_conversations(
    session_id: str = Query(..., description="Session ID to filter conversations"),
    db: AsyncSession = Depends(get_db),  # noqa: ARG001  # FastAPI dependency, part of route signature
) -> dict[str, Any]:
    """List conversations for a specific session."""
    try:
        db_mongo = mongodb_settings.get_database()
        conversations_collection = db_mongo["conversations"]

        # Find conversations for this session
        cursor = conversations_collection.find({"session_id": session_id}).sort("updated_at", -1)
        conversations = await cursor.to_list(length=100)

        conversation_list = []
        for conv in conversations:
            # Log message content lengths for debugging
            raw_messages = conv.get("messages", [])
            if raw_messages:
                msg_lengths = [len(str(m.get("content", ""))) for m in raw_messages]
                logger.info(
                    f"Retrieving conversation {conv['_id']} for session {session_id}: {len(raw_messages)} messages with lengths {msg_lengths}"  # noqa: E501
                )

                # Check for truncated messages and bullet points
                for i, msg in enumerate(raw_messages):
                    content = str(msg.get("content", ""))
                    if msg.get("role") == "assistant" and len(content) > 0:
                        # Check if content looks truncated (starts and ends abruptly)
                        if len(content) < 100 and "..." in content[-10:]:
                            logger.warning(
                                f"Message {i} may be truncated: {len(content)} chars, ends with: {content[-50:]}"  # noqa: E501
                            )

                        # Check for bullet points in content
                        has_bullets = any(char in content for char in ["•", "-", "*"])
                        if not has_bullets and len(content) > 200:
                            # Long message without bullets - might be missing them
                            logger.warning(
                                f"Message {i} is long ({len(content)} chars) but has no bullet points. First 300 chars: {content[:300]}"  # noqa: E501
                            )
                        elif has_bullets:
                            logger.info(f"Message {i} contains bullet points. Length: {len(content)} chars")

            conversation_data = {
                "id": str(conv["_id"]),
                "session_id": conv["session_id"],
                "website_url": conv.get("website_url"),
                "ended": conv.get("ended", False),
                "messages": [MessageSchema(**msg) for msg in raw_messages],
                "created_at": conv.get("created_at", datetime.utcnow()),
                "updated_at": conv.get("updated_at", datetime.utcnow()),
            }
            conversation_list.append(conversation_data)

        return {"conversations": conversation_list}

    except Exception as e:
        logger.error(f"Error listing user conversations: {e}")
        raise HTTPException(status_code=500, detail=f"Error listing conversations: {e!s}") from e


@router.get("", response_model=ConversationListResponse)
async def list_conversations(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    website_url: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> ConversationListResponse:
    """List all conversations."""
    try:
        db_mongo = mongodb_settings.get_database()
        conversations_collection = db_mongo["conversations"]

        # Build query
        query = {}
        if website_url:
            query["website_url"] = website_url

        # Get conversations
        cursor = conversations_collection.find(query).sort("updated_at", -1).skip(skip).limit(limit)
        conversations = await cursor.to_list(length=limit)

        # Get total count
        total = await conversations_collection.count_documents(query)

        # Get all session IDs to fetch form submissions
        session_ids = [conv["session_id"] for conv in conversations]

        # Fetch form submissions for these sessions
        form_submissions = {}
        if session_ids:
            result = await db.execute(
                select(FormSubmission).where(FormSubmission.session_id.in_(session_ids))
            )
            submissions = result.scalars().all()
            for submission in submissions:
                if submission.session_id:
                    form_submissions[submission.session_id] = submission

        # Convert to schema
        conversation_list = []
        for conv in conversations:
            # Get form submission for this session if exists
            form_submission = form_submissions.get(conv["session_id"])

            conversation_data = {
                "id": str(conv["_id"]),
                "session_id": conv["session_id"],
                "website_url": conv.get("website_url"),
                "user_ip": conv.get("user_ip"),
                "user_agent": conv.get("user_agent"),
                "messages": [MessageSchema(**msg) for msg in conv.get("messages", [])],
                "created_at": conv.get("created_at", datetime.utcnow()),
                "updated_at": conv.get("updated_at", datetime.utcnow()),
            }

            # Add form submission data if exists
            if form_submission:
                conversation_data["user_name"] = form_submission.name
                conversation_data["user_email"] = form_submission.email
                conversation_data["user_phone"] = form_submission.phone

            conversation_list.append(ConversationSchema(**conversation_data))

        return ConversationListResponse(conversations=conversation_list, total=total)

    except Exception as e:
        logger.error(f"Error listing conversations: {e}")
        raise HTTPException(status_code=500, detail=f"Error listing conversations: {e!s}") from e


@router.get("/{conversation_id}", response_model=ConversationSchema)
async def get_conversation(conversation_id: str, db: AsyncSession = Depends(get_db)) -> ConversationSchema:
    """Get a specific conversation by ID."""
    try:
        db_mongo = mongodb_settings.get_database()
        conversations_collection = db_mongo["conversations"]

        conversation = await conversations_collection.find_one({"_id": ObjectId(conversation_id)})

        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")

        # Get form submission for this session if exists
        form_submission = None
        session_id = conversation.get("session_id")
        if session_id:
            result = await db.execute(select(FormSubmission).where(FormSubmission.session_id == session_id))
            form_submission = result.scalar_one_or_none()

        conversation_data = {
            "id": str(conversation["_id"]),
            "session_id": conversation["session_id"],
            "website_url": conversation.get("website_url"),
            "user_ip": conversation.get("user_ip"),
            "user_agent": conversation.get("user_agent"),
            "messages": [MessageSchema(**msg) for msg in conversation.get("messages", [])],
            "created_at": conversation.get("created_at", datetime.utcnow()),
            "updated_at": conversation.get("updated_at", datetime.utcnow()),
        }

        # Add form submission data if exists
        if form_submission:
            conversation_data["user_name"] = form_submission.name
            conversation_data["user_email"] = form_submission.email
            conversation_data["user_phone"] = form_submission.phone

        return ConversationSchema(**conversation_data)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting conversation: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting conversation: {e!s}") from e


@router.delete("/{conversation_id}")
async def delete_conversation(conversation_id: str) -> dict[str, Any]:
    """Delete a conversation."""
    try:
        db = mongodb_settings.get_database()
        conversations_collection = db["conversations"]

        result = await conversations_collection.delete_one({"_id": ObjectId(conversation_id)})

        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Conversation not found")

        return {"message": "Conversation deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting conversation: {e}")
        raise HTTPException(status_code=500, detail=f"Error deleting conversation: {e!s}") from e


@router.post("/save")
async def save_conversation(
    session_id: str = Query(...),
    website_url: str | None = Query(None),
    ended: bool = Query(False),
    body: dict[str, Any] = Body(None),
) -> dict[str, Any]:
    """Save or update a conversation (ongoing or ended)."""
    try:
        # Get messages from request body
        messages = None
        if body and isinstance(body, dict) and "messages" in body:
            messages = body["messages"]

        db_mongo = mongodb_settings.get_database()
        conversations_collection = db_mongo["conversations"]

        # Find existing ongoing conversation (not ended)
        existing = await conversations_collection.find_one({"session_id": session_id, "ended": False})

        # Log the save attempt for debugging
        if existing:
            existing_messages = existing.get("messages", [])
            existing_lengths = [len(str(m.get("content", ""))) for m in existing_messages]
            logger.info(
                f"Save endpoint called for session {session_id} - existing: {len(existing_messages)} messages with lengths {existing_lengths}"  # noqa: E501
            )
        else:
            logger.info(f"Save endpoint called for session {session_id} - no existing conversation")

        conversation_data = {
            "session_id": session_id,
            "website_url": website_url,
            "ended": ended,
            "updated_at": datetime.utcnow(),
        }

        if messages:
            conversation_data["messages"] = messages

        if existing and not ended:
            # Update existing ongoing conversation
            conversation_data["created_at"] = existing.get("created_at", datetime.utcnow())

            # CRITICAL FIX: Bot API uses $push to append messages correctly with full content
            # NEVER overwrite messages that were saved by bot API - it's the source of truth
            existing_messages = existing.get("messages", [])

            if messages:
                # CRITICAL: Once bot API saves ANY message, it becomes the source of truth
                # Bot API saves user + assistant pairs using $push, preserving full content
                # Widget's saveConversationState() uses $set which would overwrite and truncate

                has_user_messages = any(m.get("role") == "user" for m in existing_messages)

                # Check if any assistant message is longer than welcome messages (bot API responses are long)
                # Welcome messages are typically < 200 chars, bot responses are usually > 200 chars
                has_long_assistant = any(
                    m.get("role") == "assistant" and len(str(m.get("content", ""))) > 200
                    for m in existing_messages
                )

                # Count messages - bot API saves in pairs (user + assistant), so 3+
                # messages means bot API has saved
                message_count_indicating_bot_api = len(existing_messages) >= 3

                # ULTRA-STRICT: If there are more than 2 messages (welcome messages),
                # bot API has definitely saved
                # OR if any message has content > 150 chars (bot responses are long,
                # welcome messages are short)
                has_any_long_content = any(len(str(m.get("content", ""))) > 150 for m in existing_messages)

                if not existing_messages:
                    # No messages yet - initial save (welcome messages only)
                    conversation_data["messages"] = messages
                    attempted_lengths = [len(str(m.get("content", ""))) for m in messages] if messages else []
                    logger.info(
                        f"Initial message save for session {session_id}: {len(messages)} messages with lengths {attempted_lengths}"  # noqa: E501
                    )
                elif (
                    has_user_messages
                    or has_long_assistant
                    or message_count_indicating_bot_api
                    or has_any_long_content
                    or len(existing_messages) > 2
                ):
                    # Bot API has already saved messages - ABSOLUTELY NEVER overwrite them
                    # The bot API is the ONLY source of truth for message content after initial welcome
                    conversation_data.pop("messages", None)

                    # Log existing message lengths vs attempted lengths for debugging
                    existing_lengths = [len(str(m.get("content", ""))) for m in existing_messages]
                    attempted_lengths = [len(str(m.get("content", ""))) for m in messages]

                    # Check for bullet points in existing vs attempted messages
                    existing_bullets = [
                        any(char in str(m.get("content", "")) for char in ["•", "-", "*"])
                        for m in existing_messages
                    ]
                    attempted_bullets = [
                        any(char in str(m.get("content", "")) for char in ["•", "-", "*"]) for m in messages
                    ]

                    # Log sample content to see if bullet points are present
                    if existing_messages:
                        last_assistant = next(
                            (m for m in reversed(existing_messages) if m.get("role") == "assistant"), None
                        )
                        if last_assistant:
                            sample_content = str(last_assistant.get("content", ""))[:200]
                            logger.info(
                                f"Sample existing assistant message content (first 200 chars): {sample_content}"  # noqa: E501
                            )

                    logger.warning(
                        f"BLOCKED message overwrite for session {session_id}. "
                        f"Existing: {len(existing_messages)} messages with lengths {existing_lengths} (has_bullets: {existing_bullets}) "  # noqa: E501
                        f"(has_user: {has_user_messages}, has_long_assistant: {has_long_assistant}, count>=3: {message_count_indicating_bot_api}, count>2: {len(existing_messages) > 2}), "  # noqa: E501
                        f"Attempted: {len(messages)} messages with lengths {attempted_lengths} (has_bullets: {attempted_bullets}). "  # noqa: E501
                        f"Bot API messages preserved - widget save blocked. Returning 200 OK but NOT updating messages."  # noqa: E501
                    )
                else:
                    # Only short welcome messages exist - safe to update (but be very careful)
                    # This should only happen if welcome messages are being updated before any bot interaction
                    conversation_data["messages"] = messages
                    logger.info(
                        f"Updating welcome messages for session {session_id} (no bot API messages yet)"
                    )
            else:
                # No messages in request - don't touch existing messages
                conversation_data.pop("messages", None)

            await conversations_collection.update_one({"_id": existing["_id"]}, {"$set": conversation_data})
            return {"conversation_id": str(existing["_id"]), "message": "Conversation updated"}
        # Create new conversation (either no existing conversation, or existing is
        # ended, or we're ending a conversation)
        conversation_data["created_at"] = datetime.utcnow()
        result = await conversations_collection.insert_one(conversation_data)
        return {"conversation_id": str(result.inserted_id), "message": "Conversation saved"}

    except Exception as e:
        logger.error(f"Error saving conversation: {e}")
        raise HTTPException(status_code=500, detail=f"Error saving conversation: {e!s}") from e


@router.post("/end")
async def end_conversation(
    session_id: str = Query(...),
    conversation_id: str | None = Query(None),
    ended: bool = Query(True),
    body: dict[str, Any] = Body(None),
) -> dict[str, Any]:
    """Mark a conversation as ended."""
    try:
        # Get messages from request body
        messages = None
        if body and isinstance(body, dict) and "messages" in body:
            messages = body["messages"]

        db_mongo = mongodb_settings.get_database()
        conversations_collection = db_mongo["conversations"]

        query: dict[str, Any] = {}
        if conversation_id:
            query["_id"] = ObjectId(conversation_id)
        else:
            query["session_id"] = session_id

        update_data = {"ended": ended, "updated_at": datetime.utcnow()}

        if messages:
            update_data["messages"] = messages

        result = await conversations_collection.update_one(query, {"$set": update_data})

        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Conversation not found")

        return {"message": "Conversation ended successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error ending conversation: {e}")
        raise HTTPException(status_code=500, detail=f"Error ending conversation: {e!s}") from e
