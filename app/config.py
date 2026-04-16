from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    secret_key: str
    google_client_id: str
    google_client_secret: str
    database_url: str = "sqlite+aiosqlite:///./edu_chat.db"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    debug: bool = False
    ollama_endpoint: str = ""
    ollama_api_key: str = ""

    model_config = {"env_file": ".env"}


settings = Settings()