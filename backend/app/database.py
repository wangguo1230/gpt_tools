from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import os
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

Base = declarative_base()


def _default_sqlite_url() -> str:
    data_dir = Path(__file__).resolve().parents[2] / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{(data_dir / 'gpt_tools.db').as_posix()}"


def database_url() -> str:
    return str(os.getenv("GPT_TOOLS_DATABASE_URL") or _default_sqlite_url()).strip()


def _connect_args(url: str) -> dict[str, object]:
    if url.startswith("sqlite:"):
        return {"check_same_thread": False}
    return {}


ENGINE = create_engine(
    database_url(),
    future=True,
    pool_pre_ping=True,
    connect_args=_connect_args(database_url()),
)
SessionLocal = sessionmaker(bind=ENGINE, autoflush=False, autocommit=False, expire_on_commit=False)


def init_database() -> None:
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=ENGINE)


@contextmanager
def session_scope() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
