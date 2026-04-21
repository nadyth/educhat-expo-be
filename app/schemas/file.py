import uuid
from datetime import datetime

from pydantic import BaseModel, field_serializer


class FileOut(BaseModel):
    id: uuid.UUID
    original_name: str
    content_type: str
    size: int
    gcs_path: str
    owner_id: uuid.UUID
    processing_status: str = "pending"
    pages_processed: int = 0
    pages_total: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}


class SignedURLResponse(BaseModel):
    url: str
    expires_in_seconds: int


class FileRename(BaseModel):
    original_name: str

    model_config = {"from_attributes": True}


class ProcessingStatusResponse(BaseModel):
    file_id: uuid.UUID
    processing_status: str
    pages_processed: int
    pages_total: int

    model_config = {"from_attributes": True, "populate_by_name": True}

    @classmethod
    def from_orm_data(cls, file_obj):
        return cls(
            file_id=file_obj.id,
            processing_status=file_obj.processing_status,
            pages_processed=file_obj.pages_processed,
            pages_total=file_obj.pages_total,
        )