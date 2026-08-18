"""MongoDB models for conversations."""

from datetime import datetime

from pydantic import BaseModel, Field


class Message(BaseModel):
    """Individual message in a conversation."""

    role: str  # "user" or "assistant"
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class Conversation(BaseModel):
    """Conversation model for MongoDB."""

    session_id: str  # Unique session ID (usually from website visitor)
    website_url: str | None = None  # Website where bot was embedded
    user_ip: str | None = None
    user_agent: str | None = None
    messages: list[Message] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        # RUF012: this is a Pydantic config class, not a model body. Annotating
        # the attribute as ClassVar could change how Pydantic reads the config,
        # so it is left as a plain assignment.
        json_schema_extra = {  # noqa: RUF012
            "example": {
                "session_id": "abc123",
                "website_url": "https://example.com",
                "messages": [
                    {"role": "user", "content": "Hello", "timestamp": "2025-01-01T00:00:00"},
                    {
                        "role": "assistant",
                        "content": "Hi! How can I help you?",
                        "timestamp": "2025-01-01T00:00:01",
                    },
                ],
            }
        }
