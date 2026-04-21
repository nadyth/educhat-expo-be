import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import get_current_user
from app.dependencies.db import get_db
from app.models.file import File
from app.models.study_config import StudyConfig
from app.models.user import User
from app.schemas.study_config import StudyConfigCreate, StudyConfigOut

router = APIRouter()


async def _get_owned_file(
    file_id: uuid.UUID, user: User, db: AsyncSession
) -> File:
    result = await db.execute(select(File).where(File.id == file_id))
    db_file = result.scalar_one_or_none()
    if db_file is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    if db_file.owner_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this file",
        )
    return db_file


@router.post(
    "/{file_id}/study-configs",
    response_model=StudyConfigOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_study_config(
    file_id: uuid.UUID,
    body: StudyConfigCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    db_file = await _get_owned_file(file_id, user, db)

    if db_file.pages_total == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File has not been processed yet; page count unknown",
        )

    if body.end_page > db_file.pages_total:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"end_page ({body.end_page}) exceeds total pages ({db_file.pages_total})",
        )

    # Check for overlapping ranges
    result = await db.execute(
        select(StudyConfig).where(StudyConfig.file_id == file_id)
    )
    existing = result.scalars().all()

    for cfg in existing:
        # Two inclusive ranges [s,e] and [s',e'] overlap if s <= e' AND s' <= e
        if body.start_page <= cfg.end_page and cfg.start_page <= body.end_page:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Overlaps with existing range {cfg.start_page}–{cfg.end_page}",
            )

    study_config = StudyConfig(
        file_id=file_id,
        start_page=body.start_page,
        end_page=body.end_page,
    )
    db.add(study_config)
    await db.commit()
    await db.refresh(study_config)
    return study_config


@router.get("/{file_id}/study-configs", response_model=list[StudyConfigOut])
async def list_study_configs(
    file_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_owned_file(file_id, user, db)

    result = await db.execute(
        select(StudyConfig)
        .where(StudyConfig.file_id == file_id)
        .order_by(StudyConfig.start_page)
    )
    return result.scalars().all()


@router.delete(
    "/{file_id}/study-configs/{config_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_study_config(
    file_id: uuid.UUID,
    config_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_owned_file(file_id, user, db)

    result = await db.execute(
        select(StudyConfig).where(
            StudyConfig.id == config_id, StudyConfig.file_id == file_id
        )
    )
    study_config = result.scalar_one_or_none()
    if study_config is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Study config not found"
        )

    await db.delete(study_config)
    await db.commit()