from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy.orm import Session

from ..database import init_database, session_scope


class ToolDatabaseUnavailable(RuntimeError):
    """独立工具数据库不可用。"""


def ensure_tool_db_ready() -> None:
    try:
        init_database()
    except Exception as exc:  # pragma: no cover
        raise ToolDatabaseUnavailable(str(exc)) from exc


@contextmanager
def tool_session_scope() -> Iterator[Session]:
    ensure_tool_db_ready()
    with session_scope() as session:
        yield session
