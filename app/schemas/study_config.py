import uuid
from datetime import datetime

from pydantic import BaseModel, model_validator


class StudyConfigCreate(BaseModel):
    start_page: int
    end_page: int

    @model_validator(mode="after")
    def validate_pages(self):
        if self.start_page < 1:
            raise ValueError("start_page must be at least 1")
        if self.start_page > self.end_page:
            raise ValueError("start_page must be less than or equal to end_page")
        return self


class StudyConfigOut(BaseModel):
    id: uuid.UUID
    file_id: uuid.UUID
    start_page: int
    end_page: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}