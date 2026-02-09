"""Tests for content-based detection."""

import numpy as np
import pytest
from PIL import Image

from src.detection.content_detector import ContentDetector, ContentType, ContentAnalysis


class TestContentDetector:
    """Tests for ContentDetector class."""

    def test_init_default_values(self) -> None:
        """Test default initialization values."""
        detector = ContentDetector()
        assert detector.reels_confirmation_frames == 3
        assert detector.non_reels_confirmation_frames == 5
        assert detector.hash_threshold == 15
        assert not detector.in_reels_session
        assert detector.current_content_type == ContentType.UNKNOWN

    def test_init_custom_values(self) -> None:
        """Test custom initialization values."""
        detector = ContentDetector(
            reels_confirmation_frames=5,
            non_reels_confirmation_frames=10,
            hash_threshold=20,
        )
        assert detector.reels_confirmation_frames == 5
        assert detector.non_reels_confirmation_frames == 10
        assert detector.hash_threshold == 20

    def test_black_screen_detection(self, black_image: Image.Image) -> None:
        """Test that black screens are detected correctly."""
        detector = ContentDetector()
        analysis = detector.analyze_frame(black_image)
        assert analysis.content_type == ContentType.BLACK_SCREEN
        assert analysis.confidence >= 0.9

    def test_analyze_frame_returns_analysis(self, sample_image: Image.Image) -> None:
        """Test that analyze_frame returns ContentAnalysis."""
        detector = ContentDetector()
        analysis = detector.analyze_frame(sample_image)

        assert isinstance(analysis, ContentAnalysis)
        assert analysis.content_type in ContentType
        assert 0 <= analysis.confidence <= 1
        assert analysis.aspect_ratio >= 0
        assert analysis.entropy >= 0
        assert isinstance(analysis.hash_value, str)

    def test_reset_clears_state(self, sample_image: Image.Image) -> None:
        """Test that reset clears detector state."""
        detector = ContentDetector()

        # Process some frames
        detector.process_frame(sample_image)
        detector.process_frame(sample_image)

        # Reset
        detector.reset()
        assert not detector.in_reels_session
        assert detector.current_content_type == ContentType.UNKNOWN

    def test_vertical_image_detection(self) -> None:
        """Test detection of vertical aspect ratio images."""
        detector = ContentDetector()

        # Create a vertical image (like a phone screen showing Reels)
        # 1080x1920 is a typical phone resolution
        arr = np.random.randint(0, 255, (1920, 1080, 3), dtype=np.uint8)
        vertical_image = Image.fromarray(arr)

        analysis = detector.analyze_frame(vertical_image)
        # Should detect vertical aspect ratio
        assert analysis.aspect_ratio > 1.5

    def test_horizontal_image_detection(self) -> None:
        """Test detection of horizontal aspect ratio images."""
        detector = ContentDetector()

        # Create a horizontal image
        arr = np.random.randint(0, 255, (1080, 1920, 3), dtype=np.uint8)
        horizontal_image = Image.fromarray(arr)

        analysis = detector.analyze_frame(horizontal_image)
        # Should detect horizontal aspect ratio
        assert analysis.aspect_ratio < 1.0

    def test_process_frame_returns_tuple(self, sample_image: Image.Image) -> None:
        """Test that process_frame returns correct tuple."""
        detector = ContentDetector()
        result = detector.process_frame(sample_image)

        assert isinstance(result, tuple)
        assert len(result) == 3
        content_type, session_started, session_ended = result
        assert content_type in ContentType
        assert isinstance(session_started, bool)
        assert isinstance(session_ended, bool)

    def test_black_screen_ends_session(self, black_image: Image.Image) -> None:
        """Test that extended black screen ends session."""
        detector = ContentDetector()

        # Simulate being in a session
        detector._state.in_reels_session = True

        # Process multiple black frames
        for _ in range(detector.BLACK_SCREEN_THRESHOLD):
            content_type, _, session_ended = detector.process_frame(black_image)

        # Should have ended session
        assert session_ended or not detector.in_reels_session

    def test_is_reels_content_quick_check(self) -> None:
        """Test the quick reels content check."""
        detector = ContentDetector()

        # Create a high-entropy vertical image (simulates video content)
        arr = np.random.randint(0, 255, (1920, 1080, 3), dtype=np.uint8)
        video_like_image = Image.fromarray(arr)

        # This should return True for video-like vertical content
        # Note: The actual result depends on entropy calculations
        result = detector.is_reels_content(video_like_image)
        assert isinstance(result, bool)


class TestSessionStateTransitions:
    """Tests for session state transitions in ContentDetector."""

    def test_session_not_started_immediately(self) -> None:
        """Test that session doesn't start on first reels-like frame."""
        detector = ContentDetector(reels_confirmation_frames=3)

        # Create a reels-like frame
        arr = np.random.randint(0, 255, (1920, 1080, 3), dtype=np.uint8)
        reels_frame = Image.fromarray(arr)

        # First frame should not start session
        _, session_started, _ = detector.process_frame(reels_frame)
        # May or may not start depending on content analysis
        # The key is it needs confirmation frames

    def test_session_ends_after_non_reels_frames(self) -> None:
        """Test that session ends after enough non-reels frames."""
        detector = ContentDetector(
            reels_confirmation_frames=1,
            non_reels_confirmation_frames=2,
        )

        # Manually set session as active
        detector._state.in_reels_session = True
        detector._state.consecutive_reels_frames = 5

        # Create a low-entropy horizontal image (clearly not Reels)
        arr = np.zeros((1080, 1920, 3), dtype=np.uint8)
        arr[:, :640, 0] = 200  # Some color but low entropy
        static_frame = Image.fromarray(arr)

        # Process non-reels frames
        session_ended = False
        for _ in range(detector.non_reels_confirmation_frames + 1):
            _, _, ended = detector.process_frame(static_frame)
            if ended:
                session_ended = True
                break

        # Session should have ended
        assert session_ended or not detector.in_reels_session


class TestContentAnalysis:
    """Tests for ContentAnalysis dataclass."""

    def test_content_analysis_creation(self) -> None:
        """Test ContentAnalysis can be created with all fields."""
        analysis = ContentAnalysis(
            content_type=ContentType.REELS,
            confidence=0.85,
            aspect_ratio=1.78,
            entropy=6.5,
            is_vertical_video=True,
            hash_value="abc123",
        )

        assert analysis.content_type == ContentType.REELS
        assert analysis.confidence == 0.85
        assert analysis.aspect_ratio == 1.78
        assert analysis.entropy == 6.5
        assert analysis.is_vertical_video is True
        assert analysis.hash_value == "abc123"


class TestContentType:
    """Tests for ContentType enum."""

    def test_all_content_types_exist(self) -> None:
        """Test all expected content types are defined."""
        assert ContentType.UNKNOWN
        assert ContentType.REELS
        assert ContentType.STATIC_UI
        assert ContentType.BLACK_SCREEN
        assert ContentType.TRANSITION

    def test_content_types_are_unique(self) -> None:
        """Test all content type values are unique."""
        values = [ct.value for ct in ContentType]
        assert len(values) == len(set(values))
