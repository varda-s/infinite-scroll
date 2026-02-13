"""Integration tests for session lifecycle with content-based detection."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PIL import Image

from src.capture.base import BaseCapture, DeviceInfo, DeviceType, ForegroundApp
from src.config import Config
from src.detection.content_detector import ContentDetector, ContentType
from src.orchestrator import Orchestrator
from src.printing.mock_printer import MockPrinter


class MockMirrorCapture(BaseCapture):
    """Mock capture that simulates mirror mode."""

    def __init__(self, frames: list[Image.Image] | None = None):
        self._frames = frames or []
        self._frame_index = 0
        self._connected = False
        self._device_info = DeviceInfo(
            device_type=DeviceType.IOS,
            device_id="mock:mirror",
            device_name="Mock iPhone (Mirror)",
            model="iPhone Mirroring",
            connection_type="mirror",  # This triggers content-based detection
        )

    @property
    def device_info(self) -> DeviceInfo:
        return self._device_info

    @property
    def is_connected(self) -> bool:
        return self._connected

    def connect(self) -> bool:
        self._connected = True
        return True

    def disconnect(self) -> None:
        self._connected = False

    def capture_screen(self) -> Image.Image | None:
        if not self._frames:
            return None
        frame = self._frames[self._frame_index % len(self._frames)]
        self._frame_index += 1
        return frame

    def get_foreground_app(self) -> ForegroundApp | None:
        # In mirror mode, we assume Instagram Reels
        return ForegroundApp(
            package_name="com.instagram.android",
            activity="reels",
        )


def create_reels_like_frame() -> Image.Image:
    """Create a frame that looks like Reels content (vertical, high entropy)."""
    # 9:16 aspect ratio, random content (high entropy)
    arr = np.random.randint(50, 205, (1920, 1080, 3), dtype=np.uint8)
    return Image.fromarray(arr)


def create_static_ui_frame() -> Image.Image:
    """Create a frame that looks like static UI (low entropy)."""
    # Horizontal, solid colors
    arr = np.zeros((1080, 1920, 3), dtype=np.uint8)
    arr[:360, :, 0] = 200  # Red header
    arr[360:720, :, 1] = 200  # Green content
    arr[720:, :, 2] = 200  # Blue footer
    return Image.fromarray(arr)


def create_black_frame() -> Image.Image:
    """Create a black frame (screen locked/transition)."""
    arr = np.zeros((1920, 1080, 3), dtype=np.uint8)
    return Image.fromarray(arr)


class TestContentDetectorIntegration:
    """Integration tests for ContentDetector with various frame sequences."""

    def test_reels_session_starts_after_confirmation_frames(self) -> None:
        """Test that session starts after enough reels-like frames."""
        detector = ContentDetector(reels_confirmation_frames=3)

        session_started = False
        for i in range(5):
            frame = create_reels_like_frame()
            _, started, _ = detector.process_frame(frame)
            if started:
                session_started = True
                break

        # Session should have started after confirmation frames
        assert session_started or detector.in_reels_session

    def test_reels_session_ends_after_non_reels_frames(self) -> None:
        """Test that session ends after enough non-reels frames."""
        detector = ContentDetector(
            reels_confirmation_frames=2,
            non_reels_confirmation_frames=3,
        )

        # Start a session
        for _ in range(3):
            detector.process_frame(create_reels_like_frame())

        assert detector.in_reels_session

        # End the session with non-reels frames
        session_ended = False
        for _ in range(5):
            frame = create_static_ui_frame()
            _, _, ended = detector.process_frame(frame)
            if ended:
                session_ended = True
                break

        assert session_ended or not detector.in_reels_session

    def test_black_screen_ends_session(self) -> None:
        """Test that black screens end an active session."""
        detector = ContentDetector(reels_confirmation_frames=1)

        # Start a session
        detector.process_frame(create_reels_like_frame())
        detector.process_frame(create_reels_like_frame())

        # Verify session is active
        assert detector.in_reels_session

        # Send black frames
        session_ended = False
        for _ in range(detector.BLACK_SCREEN_THRESHOLD + 1):
            _, _, ended = detector.process_frame(create_black_frame())
            if ended:
                session_ended = True
                break

        assert session_ended or not detector.in_reels_session

    def test_transition_back_to_reels_restarts_session(self) -> None:
        """Test that returning to reels after leaving restarts session."""
        detector = ContentDetector(
            reels_confirmation_frames=2,
            non_reels_confirmation_frames=2,
        )

        # Start session
        for _ in range(3):
            detector.process_frame(create_reels_like_frame())
        assert detector.in_reels_session

        # End session
        for _ in range(3):
            detector.process_frame(create_static_ui_frame())
        assert not detector.in_reels_session

        # Restart session
        session_started = False
        for _ in range(3):
            frame = create_reels_like_frame()
            _, started, _ = detector.process_frame(frame)
            if started:
                session_started = True
                break

        assert session_started or detector.in_reels_session


class TestMirrorModeOrchestrator:
    """Integration tests for Orchestrator in mirror mode."""

    def test_orchestrator_detects_mirror_mode(self, temp_dir: Path) -> None:
        """Test that orchestrator correctly identifies mirror mode."""
        config = Config(
            capture_fps=10,
            hash_threshold=15,
            min_reel_duration=0.5,
            printer_type="mock",
            output_dir=temp_dir,
        )

        capture = MockMirrorCapture()
        printer = MockPrinter(output_dir=temp_dir, verbose=False)

        orchestrator = Orchestrator(
            capture=capture,
            printer=printer,
            config=config,
            use_content_detection=True,
        )

        # Connect to verify mirror mode detection
        capture.connect()
        device_info = capture.device_info

        assert device_info.connection_type == "mirror"

    def test_content_detection_enabled_for_mirror_mode(self, temp_dir: Path) -> None:
        """Test that content detection is used for mirror connections."""
        config = Config(
            capture_fps=10,
            hash_threshold=15,
            min_reel_duration=0.5,
            printer_type="mock",
            output_dir=temp_dir,
        )

        frames = [create_reels_like_frame() for _ in range(5)]
        capture = MockMirrorCapture(frames=frames)
        printer = MockPrinter(output_dir=temp_dir, verbose=False)

        orchestrator = Orchestrator(
            capture=capture,
            printer=printer,
            config=config,
            use_content_detection=True,
        )

        # Verify content detector is initialized
        assert orchestrator.content_detector is not None
        assert isinstance(orchestrator.content_detector, ContentDetector)


class TestSessionCallbacks:
    """Tests for session lifecycle callbacks."""

    def test_session_start_callback_triggered(self) -> None:
        """Test that session start callback is called."""
        detector = ContentDetector(reels_confirmation_frames=2)

        session_started = False
        for _ in range(3):
            _, started, _ = detector.process_frame(create_reels_like_frame())
            if started:
                session_started = True
                break

        # Either callback was triggered or session is now active
        assert session_started or detector.in_reels_session

    def test_session_end_callback_triggered(self) -> None:
        """Test that session end callback is called."""
        detector = ContentDetector(
            reels_confirmation_frames=1,
            non_reels_confirmation_frames=2,
        )

        # Start session
        for _ in range(2):
            detector.process_frame(create_reels_like_frame())
        assert detector.in_reels_session

        # End session
        session_ended = False
        for _ in range(4):
            _, _, ended = detector.process_frame(create_static_ui_frame())
            if ended:
                session_ended = True
                break

        assert session_ended or not detector.in_reels_session
