import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.dependencies.auth import get_current_user
from app.dependencies.db import get_db
from app.models.user import User
from app.services.ollama import generate, get_models, stream_generate

router = APIRouter()


@router.get("/models")
async def list_models(
    user: User = Depends(get_current_user),
):
    try:
        models = await get_models()
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ollama API error: {e.response.text}",
        )
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not reach Ollama API: {str(e)}",
        )
    return models


class GenerateRequest(BaseModel):
    model: str
    prompt: str
    stream: bool = True
    system: Optional[str] = None
    format: Optional[str] = None
    options: Optional[dict] = None


@router.post("/generate")
async def generate_endpoint(
    body: GenerateRequest,
    user: User = Depends(get_current_user),
):
    payload = body.model_dump(exclude_none=True, exclude={"stream"})
    try:
        if body.stream:
            return StreamingResponse(
                stream_generate(payload),
                media_type="application/x-ndjson",
            )
        return await generate(payload)
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ollama API error: {e.response.text}",
        )
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not reach Ollama API: {str(e)}",
        )