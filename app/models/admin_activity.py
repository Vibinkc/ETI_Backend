from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.timeutils import utcnow

from . import Base

if TYPE_CHECKING:
    from app.models.user import User


class AdminActivity(Base):
    """Audit trail of what admins do in the console.

    Rows are written by app/services/activity_log.py and are only ever read by
    the super admin. The actor's email is denormalised so the log still reads
    correctly after an admin account is deleted.
    """

    __tablename__ = "admin_activity"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, index=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True, index=True
    )
    actor_email: Mapped[str] = mapped_column(String(255), index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)  # e.g. document.upload
    entity_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)  # human-readable summary
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    user: Mapped["User | None"] = relationship("User", foreign_keys=[user_id])
