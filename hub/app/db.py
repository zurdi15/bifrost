from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def _configure_sqlite(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_conn, _record) -> None:  # noqa: ANN001
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def init_engine(db_path: Path | None = None) -> Engine:
    global _engine, _session_factory
    path = db_path or settings.state_db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    _engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    _configure_sqlite(_engine)
    _session_factory = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def get_engine() -> Engine:
    assert _engine is not None, "init_engine() must run before get_engine()"
    return _engine


@contextmanager
def session_scope() -> Iterator[Session]:
    assert _session_factory is not None, "init_engine() must run before session_scope()"
    session = _session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Iterator[Session]:
    """FastAPI dependency."""
    with session_scope() as session:
        yield session
