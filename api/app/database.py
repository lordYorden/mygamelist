from collections.abc import Generator
from importlib import import_module

from sqlmodel import Session, SQLModel, create_engine

from .config import get_settings


engine = create_engine(get_settings().database_url, pool_pre_ping=True)


def get_db() -> Generator[Session, None, None]:
    with Session(engine) as db:
        yield db


def init_db() -> None:
    import_module(".models", package=__package__)

    SQLModel.metadata.create_all(bind=engine)
