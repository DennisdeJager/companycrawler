from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "companycrawler"
    app_env: str = "development"
    app_url: str = "http://localhost:8080"
    api_url: str = "http://localhost:8000"
    database_url: str = "postgresql+psycopg://companycrawler:companycrawler@db:5432/companycrawler"
    google_client_id: str = ""
    openai_api_key: str = ""
    openrouter_api_key: str = ""
    default_summary_provider: str = "openai"
    default_summary_model: str = "gpt-5.4-mini"
    default_embedding_provider: str = "openai"
    default_embedding_model: str = "text-embedding-3-small"
    scan_max_items: int = 500
    scan_max_file_mb: int = 25
    scan_max_depth: int = 8


@lru_cache
def get_settings() -> Settings:
    return Settings()

