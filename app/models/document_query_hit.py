from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from . import Base

if TYPE_CHECKING:
    from app.models.document import Document


class DocumentQueryHit(Base):
    """One row per document that supplied context for a single user query.

    This is what makes "which documents answer the most questions" answerable.
    A query that pulls chunks from two documents writes two rows, so counting
    rows per document gives genuine retrieval usage rather than a size proxy.
    """

    __tablename__ = "document_query_hit"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, index=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("document.id", ondelete="CASCADE"), index=True)
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(16), default="widget")  # widget | assistant
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    document: Mapped["Document"] = relationship("Document")
