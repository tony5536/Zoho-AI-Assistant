from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Zoho AI Assistant"
    debug: bool = False

    memory_db_path: Path = Path("./data/memory.db")

    # Zoho OAuth placeholders
    zoho_client_id: str = ""
    zoho_client_secret: str = ""
    zoho_redirect_uri: str = "http://localhost:8000/auth/zoho/callback"
    zoho_accounts_url: str = "https://accounts.zoho.com"
    zoho_api_domain: str = "https://projectsapi.zoho.com"
    zoho_portal_id: str = ""
    zoho_use_mock: bool = False
    frontend_url: str = "http://localhost:3000"

    openai_api_key: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
