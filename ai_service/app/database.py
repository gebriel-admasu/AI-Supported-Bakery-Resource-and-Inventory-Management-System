"""SQLAlchemy engine + session for the AI forecasting service.

We deliberately share the main backend's SQLite database so the AI service can
read sales_records directly and write its own forecasting tables into the same
schema. Each service has its own SessionLocal but talks to the same .db file.
SQLite WAL mode (already enabled by the backend) handles brief concurrent
writers without blocking.
"""

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

_db_url = settings.resolved_database_url

_connect_args = {}
_kwargs = {}

if _db_url.startswith("sqlite"):
    _connect_args = {"check_same_thread": False}
else:
    _kwargs = {"pool_pre_ping": True, "pool_size": 5, "max_overflow": 10}

engine = create_engine(_db_url, connect_args=_connect_args, **_kwargs)


if _db_url.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Declarative base for AI-owned tables.

    Kept separate from the backend's Base so Alembic for this service only
    sees the four AI tables and never accidentally touches backend-owned
    schema. (Both services still write to the same .db file.)
    """


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
