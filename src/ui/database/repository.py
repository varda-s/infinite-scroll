"""Repository for CRUD operations on Session and Receipt."""

from datetime import datetime
from typing import Optional

from sqlmodel import select

from src.ui.database.connection import get_session
from src.ui.database.models import AppConfig, Receipt, Session, User


# Default configuration values
DEFAULT_CONFIG = {
    # Detection settings
    "hash_threshold": {
        "value": "15",
        "description": "pHash difference threshold for detecting new reel (lower = more sensitive)",
        "value_type": "int",
        "category": "detection",
    },
    "min_reel_duration": {
        "value": "0.5",
        "description": "Minimum seconds to count as a valid reel view (filters quick scrolls)",
        "value_type": "float",
        "category": "detection",
    },
    "transition_frames": {
        "value": "3",
        "description": "Number of black/loading frames to wait during scroll transition",
        "value_type": "int",
        "category": "detection",
    },
    "stable_frames": {
        "value": "2",
        "description": "Consecutive similar frames needed to confirm stable content",
        "value_type": "int",
        "category": "detection",
    },
    # Capture settings
    "capture_fps": {
        "value": "24",
        "description": "Screen capture frames per second (higher = more CPU usage)",
        "value_type": "int",
        "category": "capture",
    },
    "capture_timeout": {
        "value": "5.0",
        "description": "Timeout in seconds for device operations",
        "value_type": "float",
        "category": "capture",
    },
    # Printer settings
    "printer_width": {
        "value": "384",
        "description": "Thermal printer width in pixels (384 for 58mm, 576 for 80mm)",
        "value_type": "int",
        "category": "printer",
    },
    "save_screenshots": {
        "value": "true",
        "description": "Save screenshots of each reel to disk",
        "value_type": "bool",
        "category": "printer",
    },
}


class ConfigRepository:
    """Repository for application configuration."""

    @staticmethod
    def init_defaults() -> None:
        """Initialize default configuration values if they don't exist."""
        with get_session() as db:
            for key, config in DEFAULT_CONFIG.items():
                existing = db.exec(
                    select(AppConfig).where(AppConfig.key == key)
                ).first()
                if existing is None:
                    db.add(
                        AppConfig(
                            key=key,
                            value=config["value"],
                            default_value=config["value"],
                            description=config["description"],
                            value_type=config["value_type"],
                            category=config["category"],
                        )
                    )
            db.commit()

    @staticmethod
    def get(key: str) -> Optional[str]:
        """Get a configuration value."""
        with get_session() as db:
            config = db.exec(select(AppConfig).where(AppConfig.key == key)).first()
            return config.value if config else None

    @staticmethod
    def get_typed(key: str) -> Optional[int | float | bool | str]:
        """Get a configuration value with proper type conversion."""
        with get_session() as db:
            config = db.exec(select(AppConfig).where(AppConfig.key == key)).first()
            if config is None:
                return None

            if config.value_type == "int":
                return int(config.value)
            elif config.value_type == "float":
                return float(config.value)
            elif config.value_type == "bool":
                return config.value.lower() in ("true", "1", "yes")
            else:
                return config.value

    @staticmethod
    def set(key: str, value: str) -> bool:
        """Set a configuration value."""
        with get_session() as db:
            config = db.exec(select(AppConfig).where(AppConfig.key == key)).first()
            if config is None:
                return False
            config.value = value
            db.add(config)
            db.commit()
            return True

    @staticmethod
    def get_all() -> list[AppConfig]:
        """Get all configuration values."""
        with get_session() as db:
            return list(db.exec(select(AppConfig).order_by(AppConfig.category)).all())

    @staticmethod
    def get_by_category(category: str) -> list[AppConfig]:
        """Get all configuration values in a category."""
        with get_session() as db:
            return list(
                db.exec(
                    select(AppConfig).where(AppConfig.category == category)
                ).all()
            )

    @staticmethod
    def reset_to_defaults() -> None:
        """Reset all configuration to default values."""
        with get_session() as db:
            configs = db.exec(select(AppConfig)).all()
            for config in configs:
                config.value = config.default_value
                db.add(config)
            db.commit()


class SessionRepository:
    """Repository for Session and Receipt CRUD operations."""

    @staticmethod
    def create_session(
        device_type: str,
        device_name: str,
        printer_type: str,
        user_id: Optional[int] = None,
    ) -> Session:
        """Create a new tracking session."""
        session = Session(
            start_time=datetime.now(),
            device_type=device_type,
            device_name=device_name,
            printer_type=printer_type,
            user_id=user_id,
            status="active",
        )
        with get_session() as db:
            db.add(session)
            db.commit()
            db.refresh(session)
            return session

    @staticmethod
    def get_session(session_id: int) -> Optional[Session]:
        """Get a session by ID."""
        with get_session() as db:
            return db.get(Session, session_id)

    @staticmethod
    def get_active_session() -> Optional[Session]:
        """Get the currently active session, if any."""
        with get_session() as db:
            statement = select(Session).where(Session.status == "active")
            return db.exec(statement).first()

    @staticmethod
    def get_all_sessions(limit: int = 50) -> list[Session]:
        """Get all sessions, most recent first."""
        with get_session() as db:
            statement = select(Session).order_by(Session.start_time.desc()).limit(limit)
            return list(db.exec(statement).all())

    @staticmethod
    def update_session(
        session_id: int,
        total_reels: Optional[int] = None,
        total_time_seconds: Optional[float] = None,
        receipt_content: Optional[str] = None,
        status: Optional[str] = None,
        end_time: Optional[datetime] = None,
    ) -> Optional[Session]:
        """Update a session's fields."""
        with get_session() as db:
            session = db.get(Session, session_id)
            if session is None:
                return None

            if total_reels is not None:
                session.total_reels = total_reels
            if total_time_seconds is not None:
                session.total_time_seconds = total_time_seconds
            if receipt_content is not None:
                session.receipt_content = receipt_content
            if status is not None:
                session.status = status
            if end_time is not None:
                session.end_time = end_time

            db.add(session)
            db.commit()
            db.refresh(session)
            return session

    @staticmethod
    def complete_session(
        session_id: int,
        total_reels: int,
        total_time_seconds: float,
        receipt_content: str,
    ) -> Optional[Session]:
        """Mark a session as completed with final stats."""
        return SessionRepository.update_session(
            session_id=session_id,
            total_reels=total_reels,
            total_time_seconds=total_time_seconds,
            receipt_content=receipt_content,
            status="completed",
            end_time=datetime.now(),
        )

    @staticmethod
    def add_receipt(
        session_id: int,
        reel_number: int,
        duration_seconds: float,
        screenshot_path: Optional[str] = None,
    ) -> Receipt:
        """Add a receipt to a session."""
        receipt = Receipt(
            session_id=session_id,
            reel_number=reel_number,
            duration_seconds=duration_seconds,
            timestamp=datetime.now(),
            screenshot_path=screenshot_path,
        )
        with get_session() as db:
            db.add(receipt)
            db.commit()
            db.refresh(receipt)
            return receipt

    @staticmethod
    def get_session_receipts(session_id: int) -> list[Receipt]:
        """Get all receipts for a session."""
        with get_session() as db:
            statement = (
                select(Receipt)
                .where(Receipt.session_id == session_id)
                .order_by(Receipt.reel_number)
            )
            return list(db.exec(statement).all())

    @staticmethod
    def delete_session(session_id: int) -> bool:
        """Delete a session and its receipts."""
        with get_session() as db:
            session = db.get(Session, session_id)
            if session is None:
                return False

            # Delete associated receipts
            statement = select(Receipt).where(Receipt.session_id == session_id)
            receipts = db.exec(statement).all()
            for receipt in receipts:
                db.delete(receipt)

            db.delete(session)
            db.commit()
            return True


class UserRepository:
    """Repository for User CRUD operations."""

    @staticmethod
    def create_user(
        user_id: str,
        password: str,
        display_name: str = "",
        is_admin: bool = False,
    ) -> Optional[User]:
        """Create a new user account.

        Args:
            user_id: Unique username for login.
            password: Plain text password (will be hashed).
            display_name: Display name for the user.
            is_admin: Whether user has admin privileges.

        Returns:
            Created User or None if user_id already exists.
        """
        with get_session() as db:
            # Check if user already exists
            existing = db.exec(select(User).where(User.user_id == user_id)).first()
            if existing is not None:
                return None

            salt = User.generate_salt()
            password_hash = User.hash_password(password, salt)

            user = User(
                user_id=user_id,
                password_hash=password_hash,
                salt=salt,
                display_name=display_name or user_id,
                is_admin=is_admin,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            return user

    @staticmethod
    def authenticate(user_id: str, password: str) -> Optional[User]:
        """Authenticate a user.

        Args:
            user_id: Username to authenticate.
            password: Password to verify.

        Returns:
            User if authentication successful, None otherwise.
        """
        with get_session() as db:
            user = db.exec(select(User).where(User.user_id == user_id)).first()
            if user is None:
                return None

            if not user.verify_password(password):
                return None

            # Update last login
            user.last_login = datetime.now()
            db.add(user)
            db.commit()
            db.refresh(user)
            return user

    @staticmethod
    def get_user(user_id: str) -> Optional[User]:
        """Get a user by user_id."""
        with get_session() as db:
            return db.exec(select(User).where(User.user_id == user_id)).first()

    @staticmethod
    def get_user_by_id(id: int) -> Optional[User]:
        """Get a user by database ID."""
        with get_session() as db:
            return db.get(User, id)

    @staticmethod
    def user_exists(user_id: str) -> bool:
        """Check if a user_id is already taken."""
        with get_session() as db:
            user = db.exec(select(User).where(User.user_id == user_id)).first()
            return user is not None

    @staticmethod
    def get_user_count() -> int:
        """Get total number of users."""
        with get_session() as db:
            users = db.exec(select(User)).all()
            return len(list(users))
