from datetime import datetime

from pydantic import BaseModel


class UserOut(BaseModel):
    id: int
    google_id: str
    email: str
    name: str | None
    picture_url: str | None
    created_at: datetime

    model_config = {"from_attributes": True}