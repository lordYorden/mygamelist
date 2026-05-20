from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    api_base_url: str = Field(default="http://localhost:8000")
    cookie_name: str = Field(default="BFF-SESSION")
    cookie_secure: bool = Field(default=False)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
