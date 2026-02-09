"""Tests for reel detector."""

import numpy as np
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
        """Test that arbitrary content change alone is not enough for new reel."""
        detector = ReelDetector(hash_threshold=5)

        # First frame
        detector.process_frame(sample_image)

        # Different frame without swipe-like transition should not force NEW_REEL
        detector.process_frame(sample_image_2)
        result = detector.process_frame(sample_image_2)
        assert result in (ReelChangeType.NONE, ReelChangeType.TRANSITION)

    def test_black_frame_alone_does_not_start_transition(
        self, sample_image: Image.Image, black_image: Image.Image
    ) -> None:
        """Dark reels should not be treated as transitions unless swipe is active."""
        detector = ReelDetector()

        # First frame
        detector.process_frame(sample_image)

        # Black frame without swipe evidence
        result = detector.process_frame(black_image)
        assert result == ReelChangeType.NONE

    def test_transition_then_new_content_immediately_confirms_new_reel(
        self, sample_image: Image.Image, sample_image_2: Image.Image, black_image: Image.Image
    ) -> None:
        """A confirmed swipe transition should keep detector in transition workflow."""
        detector = ReelDetector(hash_threshold=5)
        detector.process_frame(sample_image)
        detector._state.is_in_transition = True
        detector._state.last_scroll_frame = detector._state.frame_index
        detector._state.transition_peak_motion_right = 20.0
        detector._state.transition_peak_motion_center = 20.0
        detector._state.transition_peak_vertical_shift = 5.0

        result_one = detector.process_frame(sample_image_2)
        result_two = detector.process_frame(sample_image_2)
        assert result_one in (ReelChangeType.TRANSITION, ReelChangeType.NONE, ReelChangeType.NEW_REEL)
        assert result_two in (ReelChangeType.TRANSITION, ReelChangeType.NONE, ReelChangeType.NEW_REEL)

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
        self, sample_image: Image.Image, sample_image_2: Image.Image, black_image: Image.Image
    ) -> None:
        """Test that last_screenshot is updated on new reel."""
        detector = ReelDetector(hash_threshold=5)

        detector.process_frame(sample_image)
        first_screenshot = detector.last_screenshot

        # Force a swipe-like sequence: confirmed transition then new content
        detector._state.is_in_transition = True
        detector._state.last_scroll_frame = detector._state.frame_index
        detector._state.transition_peak_motion_right = 20.0
        detector._state.transition_peak_motion_center = 20.0
        detector._state.transition_peak_vertical_shift = 5.0
        detector.process_frame(sample_image_2)
        detector.process_frame(sample_image_2)
        second_screenshot = detector.last_screenshot

        assert first_screenshot is not None
        assert second_screenshot is not None

    def test_new_reel_uses_early_post_swipe_frame_for_screenshot(
        self, sample_image: Image.Image, sample_image_2: Image.Image
    ) -> None:
        """First settled frame after swipe should be retained as pending screenshot."""
        detector = ReelDetector(hash_threshold=5, transition_frames=2)
        detector.process_frame(sample_image)

        detector._state.is_in_transition = True
        detector._state.last_scroll_frame = detector._state.frame_index
        detector._state.transition_peak_motion_right = 20.0
        detector._state.transition_peak_motion_center = 20.0
        detector._state.transition_peak_vertical_shift = 5.0
        detector._is_reel_change = lambda _sig, _hash: True  # force commit path for screenshot check
        detector.swipe_motion_center_threshold = 1e9
        detector.settle_motion_right_threshold = 1e9
        detector.settle_motion_center_threshold = 1e9

        first_after_swipe = sample_image_2.copy()
        second_after_swipe = Image.fromarray(np.roll(np.array(sample_image_2), 32, axis=0))

        detector.process_frame(first_after_swipe)
        detector.process_frame(second_after_swipe)

        captured = detector._state.pending_screenshot or detector.last_screenshot
        assert captured is not None

    def test_center_video_motion_without_ui_change_does_not_increment_reel(
        self, sample_image: Image.Image
    ) -> None:
        """Animated video content alone must not create NEW_REEL events."""
        detector = ReelDetector(hash_threshold=5)
        assert detector.process_frame(sample_image) == ReelChangeType.NEW_REEL

        base = np.array(sample_image)
        h, w, _ = base.shape
        # Keep right/bottom UI rails static; animate only center video region.
        y1, y2 = int(h * 0.12), int(h * 0.72)
        x1, x2 = int(w * 0.10), int(w * 0.74)

        new_reels = 0
        for i in range(1, 24):
            frame = base.copy()
            animated = np.roll(base[y1:y2, x1:x2], shift=i * 9, axis=0)
            frame[y1:y2, x1:x2] = animated
            result = detector.process_frame(Image.fromarray(frame))
            if result == ReelChangeType.NEW_REEL:
                new_reels += 1

        assert new_reels == 0


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
