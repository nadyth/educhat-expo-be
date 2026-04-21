from pydantic import BaseModel, Field


class ExplainRequest(BaseModel):
    question: str = Field(..., min_length=1)