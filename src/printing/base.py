"""Abstract base class for printers."""

from abc import ABC, abstractmethod
from PIL import Image


class BasePrinter(ABC):
    """Abstract interface for receipt printers."""

    @abstractmethod
    def print_reel(self, screenshot: Image.Image, duration_seconds: float, reel_number: int) -> None:
        """Print a reel receipt with screenshot and duration.

        Args:
            screenshot: The screenshot image to print.
            duration_seconds: Time spent viewing this reel.
            reel_number: Sequential number of this reel in the session.
        """
        pass

    @abstractmethod
    def print_header(self, session_start: str) -> None:
        """Print session header.

        Args:
            session_start: Formatted start time of the session.
        """
        pass

    @abstractmethod
    def print_summary(self, total_reels: int, total_time_seconds: float) -> None:
        """Print session summary.

        Args:
            total_reels: Total number of reels viewed.
            total_time_seconds: Total time spent viewing reels.
        """
        pass

    @abstractmethod
    def cut(self) -> None:
        """Cut the receipt paper (or simulate cutting)."""
        pass

    @abstractmethod
    def close(self) -> None:
        """Close the printer connection and release resources."""
        pass

    def __enter__(self) -> "BasePrinter":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: type | None, exc_val: Exception | None, exc_tb: object) -> None:
        """Context manager exit."""
        self.close()

    @staticmethod
    def format_duration(seconds: float) -> str:
        """Format duration in human-readable format.

        Args:
            seconds: Duration in seconds.

        Returns:
            Formatted duration string (e.g., "1m 30s" or "45s").
        """
        if seconds < 60:
            return f"{seconds:.1f}s"
        minutes = int(seconds // 60)
        remaining_seconds = seconds % 60
        return f"{minutes}m {remaining_seconds:.0f}s"
