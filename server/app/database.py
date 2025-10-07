from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import get_config


config = get_config()
connect_args = {"check_same_thread": False} if config.database.url.startswith("sqlite") else {}
engine = create_engine(config.database.url, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, future=True)

Base = declarative_base()


def init_db() -> None:
    from . import models  # noqa: F401 - ensure models are imported for metadata

    Base.metadata.create_all(bind=engine)


@contextmanager
def session_scope():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
