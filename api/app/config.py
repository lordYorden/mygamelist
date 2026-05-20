from functools import lru_cache
import json
from time import sleep

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
import boto3
from botocore.exceptions import BotoCoreError, ClientError


class Settings(BaseSettings):
    database_url: str | None = Field(default=None)
    jwt_secret: str | None = Field(default=None)
    jwt_issuer: str = Field(default="mygamelist-api")
    jwt_algorithm: str = Field(default="HS256")
    access_token_minutes: int = Field(default=30)
    aws_region: str = Field(default="us-east-1")
    aws_access_key_id: str | None = Field(default=None)
    aws_secret_access_key: str | None = Field(default=None)
    secrets_manager_endpoint: str | None = Field(default=None)
    db_secret_name: str | None = Field(default=None)
    jwt_secret_name: str | None = Field(default=None)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    return hydrate_from_secrets_manager(settings)


def hydrate_from_secrets_manager(settings: Settings) -> Settings:
    database_url = settings.database_url
    jwt_secret = settings.jwt_secret

    if settings.db_secret_name or settings.jwt_secret_name:
        client = boto3.client(
            "secretsmanager",
            region_name=settings.aws_region,
            endpoint_url=settings.secrets_manager_endpoint,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
        )

        if settings.db_secret_name:
            database_url = read_database_url(client, settings.db_secret_name)

        if settings.jwt_secret_name:
            jwt_secret = read_jwt_secret(client, settings.jwt_secret_name)

    if not database_url:
        raise RuntimeError("DATABASE_URL or DB_SECRET_NAME must be configured")
    if not jwt_secret:
        raise RuntimeError("JWT_SECRET or JWT_SECRET_NAME must be configured")

    return settings.model_copy(update={"database_url": database_url, "jwt_secret": jwt_secret})


def read_secret_json(client, secret_name: str) -> dict:
    last_error: Exception | None = None
    for _ in range(12):
        try:
            response = client.get_secret_value(SecretId=secret_name)
            return json.loads(response["SecretString"])
        except (BotoCoreError, ClientError) as exc:
            last_error = exc
            sleep(2)
    raise RuntimeError(f"Unable to read secret {secret_name}") from last_error


def read_database_url(client, secret_name: str) -> str:
    secret = read_secret_json(client, secret_name)
    if "database_url" in secret:
        return secret["database_url"]
    if {"url", "username", "password"} <= secret.keys():
        return build_postgres_url(secret["url"], secret["username"], secret["password"])
    raise RuntimeError(f"Database secret {secret_name} must contain database_url or url/username/password")


def build_postgres_url(url: str, username: str, password: str) -> str:
    host_part = url
    for prefix in ("jdbc:postgresql://", "postgresql://"):
        if host_part.startswith(prefix):
            host_part = host_part.removeprefix(prefix)
            break
    return f"postgresql+psycopg://{username}:{password}@{host_part}"


def read_jwt_secret(client, secret_name: str) -> str:
    secret = read_secret_json(client, secret_name)
    value = secret.get("secret") or secret.get("jwt_secret")
    if not value:
        raise RuntimeError(f"JWT secret {secret_name} must contain secret or jwt_secret")
    return value
