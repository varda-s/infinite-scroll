"""SQLite database connection setup."""

from pathlib import Path

from sqlalchemy import event
from sqlmodel import Session as SQLSession
from sqlmodel import SQLModel, create_engine

# Database file location
DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"
DB_PATH = DATA_DIR / "reel_tracker.db"

_engine = None


def get_engine():
    """Get or create the database engine."""
    global _engine
    if _engine is None:
        # Ensure data directory exists
        DATA_DIR.mkdir(parents=True, exist_ok=True)

        # Create SQLite engine
        _engine = create_engine(
            f"sqlite:///{DB_PATH}",
            echo=False,
            connect_args={"check_same_thread": False},
        )

        @event.listens_for(_engine, "connect")
        def configure_sqlite(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
    return _engine


def init_db() -> None:
    """Initialize the database, creating tables if they don't exist."""
    from src.ui.database.models import Receipt, Session  # noqa: F401

    engine = get_engine()
    SQLModel.metadata.create_all(engine)


def get_session() -> SQLSession:
    """Get a new database session."""
    return SQLSession(get_engine())
