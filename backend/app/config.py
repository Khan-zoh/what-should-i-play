from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, loaded from environment or .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "What Should I Play?"
    database_url: str = "sqlite:///./wsip.db"
    cors_origins: list[str] = ["http://localhost:5173"]


settings = Settings()
