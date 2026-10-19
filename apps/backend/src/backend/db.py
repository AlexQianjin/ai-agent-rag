"""SQLAlchemy engine and session dependency.

The engine is created the first time a session is opened. Importing this
module does not read DATABASE_URL, so the agent tests and the retrieval eval
can load without a database.
"""

from collections.abc import Generator
from threading import Lock

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from backend.config import get_settings

_lock = Lock()
_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    """Return the process engine, creating it on first use."""
    global _engine
    if _engine is not None:
        return _engine
    with _lock:
        if _engine is None:
            _engine = create_engine(get_settings().database_url, pool_pre_ping=True)
    return _engine


def SessionLocal() -> Session:
    """Open a session. The engine is created the first time this runs."""
    global _session_factory
    if _session_factory is None:
        # Take the engine before the factory lock. get_engine uses the same lock.
        engine = get_engine()
        with _lock:
            if _session_factory is None:
                _session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return _session_factory()


def get_db() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def __getattr__(name: str) -> Engine:
    """`backend.db.engine` still works, and it is not created at import."""
    if name == "engine":
        return get_engine()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
