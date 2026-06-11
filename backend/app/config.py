from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, loaded from environment or .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "What Should I Play?"
    database_url: str = "sqlite:///./wsip.db"
    cors_origins: list[str] = ["http://localhost:5173"]

    # External APIs (empty defaults so tests can run without keys configured)
    steam_api_key: str = ""
    steam_user_id: str = ""
    igdb_client_id: str = ""
    igdb_client_secret: str = ""

    # HTTP timeouts (seconds)
    http_timeout_seconds: float = 10.0

    # Sentence-transformer model for game content embeddings (the [ml] extra).
    embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2"


settings = Settings()
