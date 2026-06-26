from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    api_base_url: str = Field(default="http://localhost:8000")
    cookie_name: str = Field(default="BFF-SESSION")
    cookie_secure: bool = Field(default=False)
    csrf_cookie_name: str = Field(default="XSRF-TOKEN")
    csrf_header_name: str = Field(default="X-XSRF-TOKEN")
    csrf_form_field: str = Field(default="_csrf")
    max_api_body_bytes: int = Field(default=3 * 1024 * 1024)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
