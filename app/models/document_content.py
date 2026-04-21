import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class DocumentContent(Base):
    __tablename__ = "document_contents"

    content_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    file_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("files.id", ondelete="CASCADE"), index=True
    )
    page_number: Mapped[int] = mapped_column(Integer)
    page_label: Mapped[str] = mapped_column(String(32))
    chunk_index: Mapped[int] = mapped_column(Integer)
    is_learning_material: Mapped[bool] = mapped_column(Boolean, default=True)
    content: Mapped[str] = mapped_column(Text)
    content_vector = mapped_column(Vector(1024))

    file: Mapped["File"] = relationship(back_populates="document_contents")  # noqa: F821