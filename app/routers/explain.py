import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import get_current_user
from app.dependencies.db import get_db
from app.models.file import File
from app.models.user import User
from app.schemas.explain import ExplainRequest
from app.services.explain import explain_concept

router = APIRouter()


@router.post("/{file_id}/explain")
async def explain_concept_endpoint(
    file_id: uuid.UUID,
    body: ExplainRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Validate file exists and user owns it
    result = await db.execute(select(File).where(File.id == file_id))
    db_file = result.scalar_one_or_none()
    if db_file is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    if db_file.owner_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this file",
        )

    # Validate file has been processed
    if db_file.processing_status != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File has not been processed yet",
        )
    if db_file.pages_total == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File has no pages",
        )

    return StreamingResponse(
        explain_concept(file_id, body.question, user.id, db),
        media_type="text/event-stream",
    )