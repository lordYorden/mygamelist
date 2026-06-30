from collections.abc import Generator
from importlib import import_module

from sqlalchemy import inspect, text
from sqlmodel import Session, SQLModel, create_engine

from .config import get_settings


engine = create_engine(get_settings().database_url, pool_pre_ping=True)


def get_db() -> Generator[Session, None, None]:
    with Session(engine) as db:
        yield db


def init_db() -> None:
    import_module(".models", package=__package__)

    SQLModel.metadata.create_all(bind=engine)
    ensure_webhook_title_column()


def ensure_webhook_title_column() -> None:
    inspector = inspect(engine)
    if "webhooks" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("webhooks")}
    if "title" in columns:
        return

    with engine.begin() as connection:
        connection.execute(
            text("ALTER TABLE webhooks ADD COLUMN title VARCHAR(80) NOT NULL DEFAULT 'Untitled webhook'")
        )
