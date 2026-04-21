import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies.auth import get_current_user
from app.dependencies.db import get_db
from app.dependencies.storage import require_storage_configured
from app.models.file import File
from app.models.user import User
from app.models.document_content import DocumentContent
from app.schemas.file import FileOut, FileRename, ProcessingStatusResponse, SignedURLResponse
from app.services import storage
from app.services.processing import process_pdf

router = APIRouter()

ALLOWED_TYPES = [t.strip() for t in settings.gcs_allowed_mime_types.split(",") if t.strip()]
MAX_SIZE_BYTES = settings.gcs_max_file_size_mb * 1024 * 1024


@router.post("/upload", response_model=FileOut, status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _config=Depends(require_storage_configured),
):
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type: {file.content_type}. "
            f"Allowed types: {', '.join(ALLOWED_TYPES)}",
        )

    file_data = await file.read()
    if len(file_data) > MAX_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum size of {settings.gcs_max_file_size_mb}MB",
        )
    if len(file_data) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty file",
        )

    db_file = File(
        original_name=file.filename or "untitled",
        content_type=file.content_type,
        size=len(file_data),
        gcs_path="",  # placeholder, updated after upload
        owner_id=user.id,
    )
    db.add(db_file)
    await db.flush()  # assigns the UUID id

    try:
        gcs_path = await storage.upload_file(
            file_data=file_data,
            user_id=user.id,
            doc_id=db_file.id,
            original_name=db_file.original_name,
            content_type=file.content_type,
        )
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to upload file: {e}",
        )

    db_file.gcs_path = gcs_path
    await db.commit()
    await db.refresh(db_file)

    if db_file.content_type == "application/pdf":
        background_tasks.add_task(process_pdf, db_file.id)

    return db_file


@router.get("/{file_id}/status", response_model=ProcessingStatusResponse)
async def get_processing_status(
    file_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(File).where(File.id == file_id))
    db_file = result.scalar_one_or_none()

    if db_file is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
        )

    if db_file.owner_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this file",
        )

    return ProcessingStatusResponse.from_orm_data(db_file)


@router.post("/{file_id}/process", response_model=ProcessingStatusResponse)
async def trigger_processing(
    file_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _config=Depends(require_storage_configured),
):
    result = await db.execute(select(File).where(File.id == file_id))
    db_file = result.scalar_one_or_none()

    if db_file is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
        )

    if db_file.owner_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this file",
        )

    if db_file.content_type != "application/pdf":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File is not a PDF",
        )

    if db_file.processing_status == "processing":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="File is already being processed",
        )

    # Delete existing document content rows for retry
    await db.execute(
        DocumentContent.__table__.delete().where(DocumentContent.file_id == file_id)
    )
    db_file.processing_status = "pending"
    db_file.pages_processed = 0
    db_file.pages_total = 0
    await db.commit()

    background_tasks.add_task(process_pdf, db_file.id)

    return ProcessingStatusResponse.from_orm_data(db_file)


@router.get("/{file_id}/url", response_model=SignedURLResponse)
async def get_signed_url(
    file_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _config=Depends(require_storage_configured),
):
    result = await db.execute(select(File).where(File.id == file_id))
    db_file = result.scalar_one_or_none()

    if db_file is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
        )

    if db_file.owner_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this file",
        )

    try:
        url = await storage.generate_signed_url(db_file.gcs_path)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to generate signed URL: {e}",
        )

    return SignedURLResponse(
        url=url,
        expires_in_seconds=settings.gcs_signed_url_expiration_minutes * 60,
    )


@router.get("", response_model=list[FileOut])
async def list_my_files(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(File).where(File.owner_id == user.id).order_by(File.created_at.desc())
    )
    return result.scalars().all()


@router.patch("/{file_id}/rename", response_model=FileOut)
async def rename_file(
    file_id: uuid.UUID,
    body: FileRename,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(File).where(File.id == file_id))
    db_file = result.scalar_one_or_none()

    if db_file is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
        )

    if db_file.owner_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to rename this file",
        )

    db_file.original_name = body.original_name
    await db.commit()
    await db.refresh(db_file)

    return db_file


@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_file(
    file_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _config=Depends(require_storage_configured),
):
    result = await db.execute(select(File).where(File.id == file_id))
    db_file = result.scalar_one_or_none()

    if db_file is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
        )

    if db_file.owner_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this file",
        )

    try:
        await storage.delete_file(db_file.gcs_path)
    except Exception:
        pass

    await db.delete(db_file)
    await db.commit()