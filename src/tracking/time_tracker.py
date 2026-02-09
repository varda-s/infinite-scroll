"""Time tracking for reel viewing sessions."""

from dataclasses import dataclass, field
from datetime import datetime
from time import time
from typing import Callable

from PIL import Image


@dataclass
class ReelSession:
    """Data about a single reel viewing session."""

    reel_number: int
    start_time: float
    end_time: float | None = None
    screenshot: Image.Image | None = None

    @property
    def duration(self) -> float:
        """Get duration in seconds."""
        end = self.end_time if self.end_time else time()
        return end - self.start_time

    @property
    def is_complete(self) -> bool:
        """Check if session is complete."""
        return self.end_time is not None


@dataclass
class SessionStats:
    """Statistics for a tracking session."""

    session_start: datetime
    total_reels: int = 0
    total_time: float = 0.0
    reels: list[ReelSession] = field(default_factory=list)

    @property
    def average_time_per_reel(self) -> float:
        """Get average time per reel."""
        if self.total_reels == 0:
            return 0.0
        return self.total_time / self.total_reels


class TimeTracker:
    """Track time spent on each reel."""

    def __init__(
        self,
        min_duration: float = 0.5,
        on_reel_complete: Callable[[ReelSession], None] | None = None,
    ) -> None:
        """Initialize time tracker.

        Args:
            min_duration: Minimum duration to count as a valid reel view.
            on_reel_complete: Callback when a reel viewing is complete.
        """
        self.min_duration = min_duration
        self.on_reel_complete = on_reel_complete

        self._current_reel: ReelSession | None = None
        self._completed_reels: list[ReelSession] = []
        self._session_start: datetime | None = None
        self._is_tracking = False

    @property
    def is_tracking(self) -> bool:
        """Check if currently tracking."""
        return self._is_tracking

    @property
    def current_reel(self) -> ReelSession | None:
        """Get current reel being tracked."""
        return self._current_reel

    @property
    def completed_reels(self) -> list[ReelSession]:
        """Get list of completed reel sessions."""
        return self._completed_reels.copy()

    def start_session(self) -> None:
        """Start a new tracking session."""
        self._session_start = datetime.now()
        self._current_reel = None
        self._completed_reels = []
        self._is_tracking = True

    def stop_session(self) -> SessionStats:
        """Stop tracking and return session statistics.

        Returns:
            Statistics for the completed session.
        """
        # End current reel if any
        if self._current_reel:
            self._end_current_reel()

        self._is_tracking = False

        # Calculate stats
        total_time = sum(r.duration for r in self._completed_reels)
        stats = SessionStats(
            session_start=self._session_start or datetime.now(),
            total_reels=len(self._completed_reels),
            total_time=total_time,
            reels=self._completed_reels.copy(),
        )

        return stats

    def start_new_reel(self, reel_number: int, screenshot: Image.Image | None = None) -> ReelSession | None:
        """Start tracking a new reel.

        Args:
            reel_number: Sequential number of this reel.
            screenshot: Screenshot of the reel.

        Returns:
            The previous reel session if it was valid, None otherwise.
        """
        if not self._is_tracking:
            return None

        previous_session = None

        # End previous reel if exists
        if self._current_reel:
            previous_session = self._end_current_reel()

        # Start new reel
        self._current_reel = ReelSession(
            reel_number=reel_number,
            start_time=time(),
            screenshot=screenshot,
        )

        return previous_session

    def update_screenshot(self, screenshot: Image.Image) -> None:
        """Update screenshot for current reel.

        Args:
            screenshot: New screenshot to save.
        """
        if self._current_reel:
            self._current_reel.screenshot = screenshot

    def _end_current_reel(self) -> ReelSession | None:
        """End current reel tracking.

        Returns:
            The reel session if valid, None if too short.
        """
        if not self._current_reel:
            return None

        self._current_reel.end_time = time()

        # Check if duration meets minimum
        if self._current_reel.duration >= self.min_duration:
            self._completed_reels.append(self._current_reel)

            # Call callback if set
            if self.on_reel_complete:
                self.on_reel_complete(self._current_reel)

            result = self._current_reel
        else:
            result = None

        self._current_reel = None
        return result

    def get_current_duration(self) -> float:
        """Get duration of current reel viewing.

        Returns:
            Duration in seconds, or 0 if not tracking.
        """
        if self._current_reel:
            return self._current_reel.duration
        return 0.0

    def get_total_time(self) -> float:
        """Get total time spent on completed reels.

        Returns:
            Total time in seconds.
        """
        total = sum(r.duration for r in self._completed_reels)
        if self._current_reel:
            total += self._current_reel.duration
        return total

    def get_reel_count(self) -> int:
        """Get number of completed reels.

        Returns:
            Number of reels.
        """
        return len(self._completed_reels)
