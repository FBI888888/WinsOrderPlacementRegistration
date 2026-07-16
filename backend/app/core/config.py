from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "做单账本"
    environment: str = "development"
    api_prefix: str = "/api/v1"
    database_url: str = "mysql+pymysql://wins:wins@localhost:3306/wins_order_book?charset=utf8mb4"
    jwt_secret: str = Field(default="change-me-in-production-at-least-32-bytes")
    access_token_minutes: int = 30
    refresh_token_days: int = 14
    frontend_origin: str = "http://localhost:5173"
    secure_cookies: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()