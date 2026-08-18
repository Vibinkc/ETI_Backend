"""Pydantic schemas for conversation API."""

from datetime import datetime

from pydantic import BaseModel


class MessageSchema(BaseModel):
    """Message schema for API."""

    role: str
    content: str
    timestamp: datetime


class ConversationSchema(BaseModel):
    """Conversation schema for API."""

    id: str
    session_id: str
    website_url: str | None = None
    user_ip: str | None = None
    user_agent: str | None = None
    messages: list[MessageSchema]
    created_at: datetime
    updated_at: datetime
    user_name: str | None = None
    user_email: str | None = None
    user_phone: str | None = None


class BotChatRequest(BaseModel):
    """Request schema for bot chat endpoint."""

    message: str
    session_id: str
    website_url: str | None = None
    user_ip: str | None = None
    user_agent: str | None = None


class BotChatResponse(BaseModel):
    """Response schema for bot chat endpoint."""

    response: str
    session_id: str


class ConversationListResponse(BaseModel):
    """Response schema for listing conversations."""

    conversations: list[ConversationSchema]
    total: int
