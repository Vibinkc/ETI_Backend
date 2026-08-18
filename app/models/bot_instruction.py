from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from . import Base

if TYPE_CHECKING:
    from app.models.user import User


class BotInstruction(Base):
    """The system prompt that drives the chatbot's behaviour.

    Only one row is ever used (the most recently updated one). It is created on
    first read using DEFAULT_SYSTEM_PROMPT from app/core/prompts.py.
    """

    __tablename__ = "bot_instruction"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, index=True)
    content: Mapped[str] = mapped_column(Text)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("user.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    editor: Mapped["User | None"] = relationship("User", foreign_keys=[updated_by])
