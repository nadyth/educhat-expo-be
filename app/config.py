from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    secret_key: str
    google_client_id: str
    google_client_secret: str
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/edu_chat"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    debug: bool = False
    ollama_endpoint: str = ""
    ollama_api_key: str = ""
    ollama_embedding_endpoint: str = ""
    ollama_embedding_model: str = "bge-m3"
    ollama_chat_model: str = "glm-5:cloud"
    chunk_size: int = 500
    chunk_overlap: int = 50
    tunnel: bool = False

    # GCS settings
    gcs_bucket_name: str = ""
    gcs_signed_url_expiration_minutes: int = 60
    gcs_max_file_size_mb: int = 50
    gcs_allowed_mime_types: str = (
        "image/jpeg,image/png,image/gif,image/webp,image/svg+xml,"
        "application/pdf,"
        "application/msword,"
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document,"
        "application/vnd.ms-powerpoint,"
        "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    )

    model_config = {"env_file": ".env", "extra": "ignore"}

    @property
    def database_url_sync(self) -> str:
        """Synchronous database URL for Alembic migrations."""
        return self.database_url.replace("+asyncpg", "+psycopg2")


settings = Settings()