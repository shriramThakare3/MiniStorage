"""
db/session.py
-------------
SQLAlchemy engine + session factory.

`get_db()` — FastAPI dependency that yields a session and always closes it.
`get_db_session()` — context manager for use outside request handlers.
"""
import logging
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from core.config import settings

logger = logging.getLogger(__name__)

# ── Engine ────────────────────────────────────────────────────────────────────
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,     # recycle stale connections automatically
    pool_size=10,
    max_overflow=20,
    echo=(settings.APP_ENV == "development"),
)

# ── Session factory ───────────────────────────────────────────────────────────
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


# ── FastAPI dependency ────────────────────────────────────────────────────────
def get_db():
    """Yield a DB session; rollback on error, always close."""
    db: Session = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ── General context manager ───────────────────────────────────────────────────
@contextmanager
def get_db_session():
    """Use outside FastAPI (scripts, workers, etc.)."""
    db: Session = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error("DB session error: %s", exc)
        raise
    finally:
        db.close()
