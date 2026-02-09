"""Tests for reel detector."""

import pytest
from PIL import Image

from src.detection.reel_detector import ReelDetector, ReelChangeType, ReelSession


class TestReelChangeType:
    """Tests for ReelChangeType enum."""

    def test_all_change_types_exist(self) -> None:
        """Test all expected change types are defined."""
        assert ReelChangeType.NONE
        assert ReelChangeType.NEW_REEL
        assert ReelChangeType.TRANSITION
        assert ReelChangeType.APP_CLOSED
        assert ReelChangeType.SESSION_START
        assert ReelChangeType.SESSION_END

    def test_session_types_are_distinct(self) -> None:
        """Test SESSION_START and SESSION_END are distinct values."""
        assert ReelChangeType.SESSION_START != ReelChangeType.SESSION_END
        assert ReelChangeType.SESSION_START != ReelChangeType.NEW_REEL
        assert ReelChangeType.SESSION_END != ReelChangeType.APP_CLOSED


class TestReelDetector:
    """Tests for ReelDetector class."""

    def test_init_default_values(self) -> None:
        """Test default initialization values."""
        detector = ReelDetector()
        assert detector.hash_threshold == 15
        assert detector.current_hash is None
        assert detector.last_screenshot is None

    def test_init_custom_values(self) -> None:
        """Test custom initialization values."""
        detector = ReelDetector(hash_threshold=20, transition_frames=5)
        assert detector.hash_threshold == 20

    def test_first_frame_is_new_reel(self, sample_image: Image.Image) -> None:
        """Test that first frame is detected as new reel."""
        detector = ReelDetector()
        result = detector.process_frame(sample_image)
        assert result == ReelChangeType.NEW_REEL

    def test_same_frame_no_change(self, sample_image: Image.Image) -> None:
        """Test that same frame produces no change."""
        detector = ReelDetector()

        # First frame
        detector.process_frame(sample_image)

        # Same frame again
        result = detector.process_frame(sample_image)
        assert result == ReelChangeType.NONE

    def test_different_frame_new_reel(
        self, sample_image: Image.Image, sample_image_2: Image.Image
    ) -> None:
        """Test that different frame produces new reel."""
        detector = ReelDetector(hash_threshold=5)

        # First frame
        detector.process_frame(sample_image)

        # Different frame
        result = detector.process_frame(sample_image_2)
        assert result == ReelChangeType.NEW_REEL

    def test_black_frame_is_transition(self, sample_image: Image.Image, black_image: Image.Image) -> None:
        """Test that black frame is detected as transition."""
        detector = ReelDetector()

        # First frame
        detector.process_frame(sample_image)

        # Black frame (loading/transition)
        result = detector.process_frame(black_image)
        assert result == ReelChangeType.TRANSITION

    def test_reset_clears_state(self, sample_image: Image.Image) -> None:
        """Test that reset clears detector state."""
        detector = ReelDetector()

        # Process a frame
        detector.process_frame(sample_image)
        assert detector.current_hash is not None

        # Reset
        detector.reset()
        assert detector.current_hash is None
        assert detector.last_screenshot is None

    def test_is_stable_after_multiple_same_frames(self, sample_image: Image.Image) -> None:
        """Test stability detection after multiple same frames."""
        detector = ReelDetector(stable_frames=2)

        # Process same frame multiple times
        detector.process_frame(sample_image)
        assert not detector.is_stable()  # Only 1 frame

        detector.process_frame(sample_image)
        assert detector.is_stable()  # 2 frames now

    def test_get_stable_screenshot(self, sample_image: Image.Image) -> None:
        """Test getting stable screenshot."""
        detector = ReelDetector(stable_frames=2)

        # Process same frame to reach stability
        detector.process_frame(sample_image)
        detector.process_frame(sample_image)

        screenshot = detector.get_stable_screenshot()
        assert screenshot is not None

    def test_last_screenshot_updated_on_new_reel(
        self, sample_image: Image.Image, sample_image_2: Image.Image
    ) -> None:
        """Test that last_screenshot is updated on new reel."""
        detector = ReelDetector(hash_threshold=5)

        detector.process_frame(sample_image)
        first_screenshot = detector.last_screenshot

        detector.process_frame(sample_image_2)
        second_screenshot = detector.last_screenshot

        assert first_screenshot is not None
        assert second_screenshot is not None
        # Screenshots should be different objects
        assert first_screenshot is not second_screenshot


class TestReelSession:
    """Tests for ReelSession class."""

    def test_session_starts_inactive(self) -> None:
        """Test that session starts inactive."""
        detector = ReelDetector()
        session = ReelSession(detector)
        assert not session.is_active
        assert session.reel_count == 0

    def test_session_start(self) -> None:
        """Test starting a session."""
        detector = ReelDetector()
        session = ReelSession(detector)

        session.start()
        assert session.is_active
        assert session.reel_count == 0

    def test_session_stop(self) -> None:
        """Test stopping a session."""
        detector = ReelDetector()
        session = ReelSession(detector)

        session.start()
        session.stop()
        assert not session.is_active

    def test_process_frame_increments_count(self, sample_image: Image.Image) -> None:
        """Test that processing frames increments reel count."""
        detector = ReelDetector()
        session = ReelSession(detector)
        session.start()

        change_type, reel_num = session.process_frame(sample_image)
        assert change_type == ReelChangeType.NEW_REEL
        assert reel_num == 1
        assert session.reel_count == 1

    def test_process_frame_inactive_returns_none(self, sample_image: Image.Image) -> None:
        """Test that inactive session returns NONE."""
        detector = ReelDetector()
        session = ReelSession(detector)
        # Don't start session

        change_type, reel_num = session.process_frame(sample_image)
        assert change_type == ReelChangeType.NONE
        assert reel_num == 0
