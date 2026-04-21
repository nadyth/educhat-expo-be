import uuid
import asyncio
from datetime import timedelta

from google.cloud import storage

from app.config import settings

_client: storage.Client | None = None


def _get_client() -> storage.Client:
    global _client
    if _client is None:
        _client = storage.Client()
    return _client


def _get_bucket() -> storage.Bucket:
    return _get_client().bucket(settings.gcs_bucket_name)


def _build_object_name(*, user_id: uuid.UUID, doc_id: uuid.UUID, original_name: str) -> str:
    return f"edu-chat-android-app/user_docs/{user_id}/{doc_id}/{original_name}"


async def upload_file(*, file_data: bytes, user_id: uuid.UUID, doc_id: uuid.UUID, original_name: str, content_type: str) -> str:
    object_name = _build_object_name(user_id=user_id, doc_id=doc_id, original_name=original_name)

    def _upload():
        blob = _get_bucket().blob(object_name)
        blob.upload_from_string(file_data, content_type=content_type)
        return object_name

    return await asyncio.to_thread(_upload)


async def delete_file(gcs_path: str) -> None:
    def _delete():
        blob = _get_bucket().blob(gcs_path)
        blob.delete()

    await asyncio.to_thread(_delete)


async def generate_signed_url(gcs_path: str) -> str:
    def _sign():
        blob = _get_bucket().blob(gcs_path)
        return blob.generate_signed_url(
            version="v4",
            expiration=timedelta(minutes=settings.gcs_signed_url_expiration_minutes),
            method="GET",
        )

    return await asyncio.to_thread(_sign)