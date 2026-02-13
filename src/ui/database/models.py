"""SQLModel definitions for Session and Receipt."""

import hashlib
import secrets
from datetime import datetime
from typing import Optional

from sqlmodel import Field, Relationship, SQLModel


class User(SQLModel, table=True):
    """User account for authentication."""

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str = Field(unique=True, index=True)  # Login username
    password_hash: str
    salt: str
    display_name: str = ""
    created_at: datetime = Field(default_factory=datetime.now)
    last_login: Optional[datetime] = None
    is_admin: bool = False

    @staticmethod
    def hash_password(password: str, salt: str) -> str:
        """Hash a password with salt."""
        return hashlib.sha256((password + salt).encode()).hexdigest()

    @staticmethod
    def generate_salt() -> str:
        """Generate a random salt."""
        return secrets.token_hex(16)

    def verify_password(self, password: str) -> bool:
        """Verify a password against the stored hash."""
        return self.password_hash == self.hash_password(password, self.salt)


class AppConfig(SQLModel, table=True):
    """Persistent application configuration."""

    id: Optional[int] = Field(default=None, primary_key=True)
    key: str = Field(unique=True, index=True)
    value: str
    description: str = ""
    default_value: str = ""
    value_type: str = "str"  # "int", "float", "bool", "str"
    category: str = "general"  # "detection", "capture", "printer", "general"


class Session(SQLModel, table=True):
    """Represents a tracking session."""

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, foreign_key="user.id", index=True)
    start_time: datetime
    end_time: Optional[datetime] = None
    device_type: str  # "android", "ios", "mock"
    device_name: str
    printer_type: str  # "mock", "rongta"
    total_reels: int = 0
    total_time_seconds: float = 0.0
    receipt_content: Optional[str] = None  # Full receipt text
    status: str = "active"  # "active", "completed"

    receipts: list["Receipt"] = Relationship(back_populates="session")


class Receipt(SQLModel, table=True):
    """Represents a single reel receipt within a session."""

    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="session.id")
    reel_number: int
    duration_seconds: float
    timestamp: datetime
    screenshot_path: Optional[str] = None

    session: Optional[Session] = Relationship(back_populates="receipts")
