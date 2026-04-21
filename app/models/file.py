import uuid
from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class File(Base):
    __tablename__ = "files"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    original_name: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(128))
    size: Mapped[int] = mapped_column(BigInteger)
    gcs_path: Mapped[str] = mapped_column(String(512), unique=True, index=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    processing_status: Mapped[str] = mapped_column(String(32), default="pending")
    pages_processed: Mapped[int] = mapped_column(Integer, default=0)
    pages_total: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    owner: Mapped["User"] = relationship(back_populates="files")  # noqa: F821
    document_contents: Mapped[list["DocumentContent"]] = relationship(back_populates="file", cascade="all, delete-orphan")  # noqa: F821
    study_configs: Mapped[list["StudyConfig"]] = relationship(back_populates="file", cascade="all, delete-orphan")  # noqa: F821