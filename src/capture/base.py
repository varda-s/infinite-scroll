"""Abstract base class for screen capture."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum, auto

from PIL import Image


class DeviceType(Enum):
    """Type of connected device."""

    IOS = auto()
    MOCK = auto()


@dataclass
class DeviceInfo:
    """Information about a connected device."""

    device_type: DeviceType
    device_id: str
    device_name: str
    model: str | None = None
    os_version: str | None = None
    connection_type: str = "usb"  # "usb" or "mirror"


@dataclass
class ForegroundApp:
    """Information about the current foreground app."""

    package_name: str
    activity: str | None = None


class BaseCapture(ABC):
    """Abstract interface for screen capture from mobile devices."""

    @property
    @abstractmethod
    def device_info(self) -> DeviceInfo:
        """Get information about the connected device."""
        pass

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """Check if device is connected."""
        pass

    @abstractmethod
    def connect(self) -> bool:
        """Connect to the device.

        Returns:
            True if connection successful.
        """
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Disconnect from the device."""
        pass

    @abstractmethod
    def capture_screen(self) -> Image.Image | None:
        """Capture current screen.

        Returns:
            PIL Image of the screen, or None if capture failed.
        """
        pass

    @abstractmethod
    def get_foreground_app(self) -> ForegroundApp | None:
        """Get information about the current foreground app.

        Returns:
            ForegroundApp info or None if unable to determine.
        """
        pass

    def __enter__(self) -> "BaseCapture":
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type: type | None, exc_val: Exception | None, exc_tb: object) -> None:
        """Context manager exit."""
        self.disconnect()
