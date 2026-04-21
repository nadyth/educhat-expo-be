import uuid
from datetime import datetime

from pydantic import BaseModel


class UserOut(BaseModel):
    id: uuid.UUID
    google_id: str
    email: str
    name: str | None
    picture_url: str | None
    created_at: datetime

    model_config = {"from_attributes": True}