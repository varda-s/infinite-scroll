"""SQLite database connection setup."""

from pathlib import Path

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
    return _engine


def init_db() -> None:
    """Initialize the database, creating tables if they don't exist."""
    from src.ui.database.models import Receipt, Session  # noqa: F401

    engine = get_engine()
    SQLModel.metadata.create_all(engine)


def get_session() -> SQLSession:
    """Get a new database session."""
    return SQLSession(get_engine())
