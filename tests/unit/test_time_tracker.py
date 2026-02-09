"""Tests for time tracker."""

import time as time_module

import pytest
from PIL import Image

from src.tracking.time_tracker import TimeTracker, ReelSession, SessionStats


class TestReelSession:
    """Tests for ReelSession dataclass."""

    def test_session_duration_while_active(self) -> None:
        """Test duration calculation while session is active."""
        now = time_module.time()
        session = ReelSession(reel_number=1, start_time=now - 5)

        # Duration should be approximately 5 seconds
        assert 4.9 < session.duration < 5.2

    def test_session_duration_when_complete(self) -> None:
        """Test duration calculation when session is complete."""
        session = ReelSession(
            reel_number=1,
            start_time=100.0,
            end_time=110.0,
        )

        assert session.duration == 10.0
        assert session.is_complete is True

    def test_session_not_complete_without_end_time(self) -> None:
        """Test that session is not complete without end time."""
        session = ReelSession(reel_number=1, start_time=100.0)
        assert session.is_complete is False


class TestTimeTracker:
    """Tests for TimeTracker class."""

    def test_init_default_values(self) -> None:
        """Test default initialization."""
        tracker = TimeTracker()
        assert tracker.min_duration == 0.5
        assert not tracker.is_tracking
        assert tracker.current_reel is None

    def test_init_custom_min_duration(self) -> None:
        """Test custom min_duration."""
        tracker = TimeTracker(min_duration=2.0)
        assert tracker.min_duration == 2.0

    def test_start_session(self) -> None:
        """Test starting a tracking session."""
        tracker = TimeTracker()
        tracker.start_session()

        assert tracker.is_tracking
        assert tracker.current_reel is None
        assert len(tracker.completed_reels) == 0

    def test_start_new_reel(self, sample_image: Image.Image) -> None:
        """Test starting a new reel."""
        tracker = TimeTracker()
        tracker.start_session()

        prev = tracker.start_new_reel(reel_number=1, screenshot=sample_image)

        assert prev is None  # No previous reel
        assert tracker.current_reel is not None
        assert tracker.current_reel.reel_number == 1
        assert tracker.current_reel.screenshot is not None

    def test_start_new_reel_ends_previous(self, sample_image: Image.Image) -> None:
        """Test that starting new reel ends the previous one."""
        tracker = TimeTracker(min_duration=0)  # Accept all durations
        tracker.start_session()

        # Start first reel
        tracker.start_new_reel(reel_number=1, screenshot=sample_image)
        time_module.sleep(0.1)  # Small delay

        # Start second reel
        prev = tracker.start_new_reel(reel_number=2, screenshot=sample_image)

        assert prev is not None
        assert prev.reel_number == 1
        assert prev.is_complete
        assert len(tracker.completed_reels) == 1

    def test_min_duration_filtering(self, sample_image: Image.Image) -> None:
        """Test that short reels are filtered out."""
        tracker = TimeTracker(min_duration=1.0)  # 1 second minimum
        tracker.start_session()

        # Start first reel
        tracker.start_new_reel(reel_number=1, screenshot=sample_image)
        # Immediately start second (first is too short)

        prev = tracker.start_new_reel(reel_number=2, screenshot=sample_image)

        assert prev is None  # Too short, filtered out
        assert len(tracker.completed_reels) == 0

    def test_stop_session_returns_stats(self, sample_image: Image.Image) -> None:
        """Test that stopping session returns statistics."""
        tracker = TimeTracker(min_duration=0)
        tracker.start_session()

        tracker.start_new_reel(reel_number=1, screenshot=sample_image)
        time_module.sleep(0.1)

        stats = tracker.stop_session()

        assert isinstance(stats, SessionStats)
        assert stats.total_reels == 1
        assert stats.total_time > 0

    def test_callback_called_on_reel_complete(self, sample_image: Image.Image) -> None:
        """Test that callback is called when reel completes."""
        completed_reels: list[ReelSession] = []

        def on_complete(session: ReelSession) -> None:
            completed_reels.append(session)

        tracker = TimeTracker(min_duration=0, on_reel_complete=on_complete)
        tracker.start_session()

        tracker.start_new_reel(reel_number=1, screenshot=sample_image)
        tracker.start_new_reel(reel_number=2, screenshot=sample_image)

        assert len(completed_reels) == 1
        assert completed_reels[0].reel_number == 1

    def test_update_screenshot(self, sample_image: Image.Image) -> None:
        """Test updating screenshot for current reel."""
        tracker = TimeTracker()
        tracker.start_session()

        tracker.start_new_reel(reel_number=1, screenshot=None)
        assert tracker.current_reel is not None
        assert tracker.current_reel.screenshot is None

        tracker.update_screenshot(sample_image)
        assert tracker.current_reel.screenshot is not None

    def test_get_current_duration(self, sample_image: Image.Image) -> None:
        """Test getting current reel duration."""
        tracker = TimeTracker()
        tracker.start_session()

        # No current reel
        assert tracker.get_current_duration() == 0.0

        tracker.start_new_reel(reel_number=1, screenshot=sample_image)
        time_module.sleep(0.1)

        duration = tracker.get_current_duration()
        assert duration > 0

    def test_get_total_time(self, sample_image: Image.Image) -> None:
        """Test getting total time across all reels."""
        tracker = TimeTracker(min_duration=0)
        tracker.start_session()

        tracker.start_new_reel(reel_number=1, screenshot=sample_image)
        time_module.sleep(0.1)

        tracker.start_new_reel(reel_number=2, screenshot=sample_image)
        time_module.sleep(0.1)

        total = tracker.get_total_time()
        assert total > 0.15  # Should be sum of both reels

    def test_get_reel_count(self, sample_image: Image.Image) -> None:
        """Test getting completed reel count."""
        tracker = TimeTracker(min_duration=0)
        tracker.start_session()

        assert tracker.get_reel_count() == 0

        tracker.start_new_reel(reel_number=1, screenshot=sample_image)
        tracker.start_new_reel(reel_number=2, screenshot=sample_image)

        assert tracker.get_reel_count() == 1  # First reel completed

    def test_not_tracking_prevents_new_reels(self, sample_image: Image.Image) -> None:
        """Test that new reels can't be started when not tracking."""
        tracker = TimeTracker()
        # Don't start session

        result = tracker.start_new_reel(reel_number=1, screenshot=sample_image)
        assert result is None
        assert tracker.current_reel is None


class TestSessionStats:
    """Tests for SessionStats dataclass."""

    def test_average_time_per_reel_with_reels(self) -> None:
        """Test average calculation with reels."""
        from datetime import datetime

        stats = SessionStats(
            session_start=datetime.now(),
            total_reels=4,
            total_time=20.0,
        )

        assert stats.average_time_per_reel == 5.0

    def test_average_time_per_reel_no_reels(self) -> None:
        """Test average calculation with no reels."""
        from datetime import datetime

        stats = SessionStats(
            session_start=datetime.now(),
            total_reels=0,
            total_time=0.0,
        )

        assert stats.average_time_per_reel == 0.0
