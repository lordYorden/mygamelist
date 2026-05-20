from collections.abc import Generator

from sqlmodel import Session, SQLModel, create_engine

from .config import get_settings


engine = create_engine(get_settings().database_url, pool_pre_ping=True)


def get_db() -> Generator[Session, None, None]:
    with Session(engine) as db:
        yield db


def init_db() -> None:
    from . import models  # noqa: F401

    SQLModel.metadata.create_all(bind=engine)
