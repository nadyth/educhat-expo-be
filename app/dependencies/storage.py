from fastapi import HTTPException, status

from app.config import settings


def require_storage_configured():
    if not settings.gcs_bucket_name:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="File storage is not configured",
        )