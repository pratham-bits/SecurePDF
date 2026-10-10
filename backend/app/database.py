"""Database configuration for the SecurePDF backend."""

import os
from app import config  # noqa: F401
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from app import config as _config

def get_database_url() -> str:
    """Read the required database URL from the process environment."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL environment variable is required.")
    return database_url


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""


engine = create_engine(get_database_url(), pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Session:
    """Provide a database session for a single request."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
