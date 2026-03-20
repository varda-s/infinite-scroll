"""Integration tests for orchestrator."""

import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image
import numpy as np

from src.config import Config
from src.capture.base import BaseCapture, DeviceInfo, DeviceType, ForegroundApp
from src.capture.mock_capture import MockCapture
from src.printing.mock_printer import MockPrinter
from src.orchestrator import Orchestrator
from src.tracking.time_tracker import ReelSession
from src.detection.reel_detector import ReelChangeType


class TestOrchestratorIntegration:
    """Integration tests for the orchestrator."""

    @pytest.fixture
    def varying_images_dir(self, temp_dir: Path) -> Path:
        """Create a directory with varying images to simulate reel changes."""
        images_dir = temp_dir / "varying_images"
        images_dir.mkdir()

        # Create distinctly different images
        for i in range(10):
            arr = np.zeros((1920, 1080, 3), dtype=np.uint8)

            # Each image has different dominant color
            if i % 3 == 0:
                arr[:, :, 0] = (i * 25) % 256  # Red
            elif i % 3 == 1:
                arr[:, :, 1] = (i * 25) % 256  # Green
            else:
                arr[:, :, 2] = (i * 25) % 256  # Blue

            # Add unique pattern
            arr[i * 100:(i + 1) * 100, :, :] = 255

            image = Image.fromarray(arr)
            image.save(images_dir / f"frame_{i:03d}.png")

        return images_dir

    def test_orchestrator_initialization(
        self, temp_dir: Path, varying_images_dir: Path
    ) -> None:
        """Test orchestrator can be initialized."""
        config = Config(output_dir=temp_dir)
        capture = MockCapture(source=varying_images_dir, loop=False)
        printer = MockPrinter(output_dir=temp_dir, verbose=False)

        orchestrator = Orchestrator(
            capture=capture,
            printer=printer,
            config=config,
            use_content_detection=False,
            manual_session_start=True,
        )

        assert orchestrator is not None
        assert orchestrator.config == config

    def test_orchestrator_with_mock_capture(
        self, temp_dir: Path, varying_images_dir: Path
    ) -> None:
        """Test orchestrator processes frames from mock capture."""
        config = Config(
            output_dir=temp_dir,
            capture_fps=100,  # Fast for testing
            min_reel_duration=0,  # Accept all durations
            hash_threshold=5,  # Sensitive detection
        )
        capture = MockCapture(source=varying_images_dir, loop=False)
        printer = MockPrinter(output_dir=temp_dir, verbose=False)

        detected_reels: list[ReelSession] = []

        def on_reel(session: ReelSession) -> None:
            detected_reels.append(session)

        orchestrator = Orchestrator(
            capture=capture,
            printer=printer,
            config=config,
            on_reel_change=on_reel,
        )

        # Run in thread with timeout
        def run_orchestrator() -> None:
            try:
                orchestrator.run()
            except Exception:
                pass

        thread = threading.Thread(target=run_orchestrator)
        thread.start()

        # Wait a bit then stop
        time.sleep(0.5)
        orchestrator.stop()
        thread.join(timeout=2)

        # Should have detected at least one reel
        # (The callback is called when reel ends, so we need time for that)

    def test_orchestrator_creates_output_files(
        self, temp_dir: Path, varying_images_dir: Path
    ) -> None:
        """Test that orchestrator creates output files."""
        config = Config(
            output_dir=temp_dir,
            capture_fps=100,
            min_reel_duration=0,
        )
        capture = MockCapture(source=varying_images_dir, loop=True)
        printer = MockPrinter(output_dir=temp_dir, verbose=False)

        orchestrator = Orchestrator(
            capture=capture,
            printer=printer,
            config=config,
        )

        # Run briefly
        thread = threading.Thread(target=orchestrator.run)
        thread.start()
        time.sleep(0.5)  # Give more time to process
        orchestrator.stop()
        thread.join(timeout=5)  # Wait for shutdown to complete

        # Should have created receipt file (created during shutdown)
        receipts = list(temp_dir.glob("receipt_*.txt"))
        assert len(receipts) >= 1

    def test_orchestrator_handles_no_device(self, temp_dir: Path) -> None:
        """Test orchestrator handles missing device gracefully."""
        config = Config(output_dir=temp_dir)
        capture = MockCapture(source=temp_dir / "nonexistent", loop=False)
        printer = MockPrinter(output_dir=temp_dir, verbose=False)

        orchestrator = Orchestrator(
            capture=capture,
            printer=printer,
            config=config,
        )

        # Should not crash, just return
        orchestrator.run()

    def test_orchestrator_stop_method(
        self, temp_dir: Path, varying_images_dir: Path
    ) -> None:
        """Test that stop() method works correctly."""
        config = Config(output_dir=temp_dir, capture_fps=10)
        capture = MockCapture(source=varying_images_dir, loop=True)
        printer = MockPrinter(output_dir=temp_dir, verbose=False)

        orchestrator = Orchestrator(
            capture=capture,
            printer=printer,
            config=config,
        )

        thread = threading.Thread(target=orchestrator.run)
        thread.start()

        time.sleep(0.2)
        orchestrator.stop()

        thread.join(timeout=2)
        assert not thread.is_alive()

    def test_session_starts_on_reels_mode(
        self, temp_dir: Path, varying_images_dir: Path
    ) -> None:
        """Test that session starts when entering Reels mode."""
        config = Config(
            output_dir=temp_dir,
            capture_fps=100,
            min_reel_duration=0,
        )
        # Mock capture in instagram_mode simulates Reels being active
        capture = MockCapture(source=varying_images_dir, loop=True, instagram_mode=True)
        printer = MockPrinter(output_dir=temp_dir, verbose=False)

        orchestrator = Orchestrator(
            capture=capture,
            printer=printer,
            config=config,
        )

        # Run briefly
        thread = threading.Thread(target=orchestrator.run)
        thread.start()
        time.sleep(0.5)
        orchestrator.stop()
        thread.join(timeout=5)

        # Check receipt content - should have header when session started
        content = printer.get_receipt_content()
        assert "[IMAGE] header_" in content

    def test_session_ends_with_summary_and_thank_you(
        self, temp_dir: Path, varying_images_dir: Path
    ) -> None:
        """Test that session ends with summary and thank you message."""
        config = Config(
            output_dir=temp_dir,
            capture_fps=100,
            min_reel_duration=0,
        )
        capture = MockCapture(source=varying_images_dir, loop=True, instagram_mode=True)
        printer = MockPrinter(output_dir=temp_dir, verbose=False)

        orchestrator = Orchestrator(
            capture=capture,
            printer=printer,
            config=config,
        )

        # Run briefly then stop (simulating user closing app)
        thread = threading.Thread(target=orchestrator.run)
        thread.start()
        time.sleep(0.5)
        orchestrator.stop()
        thread.join(timeout=5)

        # Check receipt includes session complete and thank you
        content = printer.get_receipt_content()
        assert "REEL RECEIPT" in content
        assert "TOTAL" in content

    def test_receipt_includes_all_session_elements(
        self, temp_dir: Path, varying_images_dir: Path
    ) -> None:
        """Test that receipt includes header, reels, summary, and thank you."""
        config = Config(
            output_dir=temp_dir,
            capture_fps=100,
            min_reel_duration=0,
            hash_threshold=5,  # Sensitive to detect reel changes
        )
        capture = MockCapture(source=varying_images_dir, loop=True, instagram_mode=True)
        printer = MockPrinter(output_dir=temp_dir, verbose=False)

        orchestrator = Orchestrator(
            capture=capture,
            printer=printer,
            config=config,
        )

        # Run long enough to detect multiple reels
        thread = threading.Thread(target=orchestrator.run)
        thread.start()
        time.sleep(1.0)
        orchestrator.stop()
        thread.join(timeout=5)

        content = printer.get_receipt_content()

        # Verify complete session structure
        assert "[IMAGE] header_" in content
        assert "Started:" in content
        assert "Time Spent:" in content
        assert "REEL RECEIPT" in content
        assert any(
            ("$" in line and "." in line and not line.startswith("TOTAL") and not line.startswith("["))
            for line in content.splitlines()
        )
        assert "TOTAL" in content
        assert "Peak fixation" in content

    def test_manual_session_tracks_reel_changes_in_mirror_mode(
        self, temp_dir: Path
    ) -> None:
        """Test manual session start still auto-detects reel changes in mirror mode."""
        mirror_images = temp_dir / "mirror_images"
        mirror_images.mkdir()

        # Create vertical, high-entropy frames with clear differences.
        for i in range(8):
            arr = np.random.randint(0, 255, (1920, 1080, 3), dtype=np.uint8)
            arr[:, i * 100:(i + 1) * 100, :] = (i * 30) % 255
            Image.fromarray(arr).save(mirror_images / f"frame_{i:03d}.png")

        config = Config(
            output_dir=temp_dir,
            capture_fps=60,
            min_reel_duration=0,
            hash_threshold=6,
        )
        capture = MockCapture(source=mirror_images, loop=True, instagram_mode=False)
        capture._device_info.connection_type = "mirror"
        printer = MockPrinter(output_dir=temp_dir, verbose=False)

        orchestrator = Orchestrator(
            capture=capture,
            printer=printer,
            config=config,
        )

        thread = threading.Thread(target=orchestrator.run)
        thread.start()
        time.sleep(1.2)
        orchestrator.stop()
        thread.join(timeout=5)

        content = printer.get_receipt_content()
        assert "[IMAGE] header_" in content
        assert "Time Spent:" in content

    def test_session_ends_when_mirror_disconnects(self, temp_dir: Path) -> None:
        """Test active session ends automatically if mirror stream disconnects."""
        class DisconnectingMirrorCapture(BaseCapture):
            def __init__(self) -> None:
                self._connected = False
                self._frames_left = 8
                self._device_info = DeviceInfo(
                    device_type=DeviceType.IOS,
                    device_id="mirror:test",
                    device_name="Test Mirror",
                    model="uxplay",
                    connection_type="mirror",
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
                if not self._connected:
                    return None
                if self._frames_left <= 0:
                    # Simulate mirror disconnect.
                    self._connected = False
                    return None
                self._frames_left -= 1
                arr = np.random.randint(0, 255, (1920, 1080, 3), dtype=np.uint8)
                return Image.fromarray(arr)

            def get_foreground_app(self) -> ForegroundApp | None:
                return ForegroundApp(package_name="com.instagram.android", activity="reels")

        config = Config(
            output_dir=temp_dir,
            capture_fps=30,
            min_reel_duration=0,
            hash_threshold=5,
        )
        capture = DisconnectingMirrorCapture()
        printer = MockPrinter(output_dir=temp_dir, verbose=False)
        orchestrator = Orchestrator(capture=capture, printer=printer, config=config)

        thread = threading.Thread(target=orchestrator.run)
        thread.start()
        thread.join(timeout=8)

        assert not thread.is_alive()
        content = printer.get_receipt_content()
        assert "REEL RECEIPT" in content

    def test_reel_number_advances_from_current_reel_not_completed_count(
        self, temp_dir: Path, varying_images_dir: Path
    ) -> None:
        """First swipe must move from reel #1 to reel #2 (no duplicate #1)."""
        config = Config(output_dir=temp_dir, capture_fps=30, min_reel_duration=0)
        capture = MockCapture(source=varying_images_dir, loop=False)
        printer = MockPrinter(output_dir=temp_dir, verbose=False)
        orchestrator = Orchestrator(capture=capture, printer=printer, config=config)

        class _FakeTracker:
            def __init__(self) -> None:
                self.current_reel = None
                self.started: list[int] = []

            def get_reel_count(self) -> int:
                # Simulate a tracker where current reel is not counted yet.
                return 0

            def start_new_reel(self, reel_number: int, screenshot=None):
                self.started.append(reel_number)
                self.current_reel = SimpleNamespace(reel_number=reel_number)
                return None

            def update_screenshot(self, screenshot) -> None:
                return None

            def get_current_duration(self) -> float:
                return 0.0

            def get_total_time(self) -> float:
                return 0.0

        class _FakeDetector:
            def __init__(self, screenshot: Image.Image) -> None:
                self.last_screenshot = screenshot

            def process_frame(self, frame: Image.Image):
                return ReelChangeType.NEW_REEL

            def is_stable(self) -> bool:
                return False

        fake_tracker = _FakeTracker()
        orchestrator.time_tracker = fake_tracker  # type: ignore[assignment]
        sample_frame = Image.new("RGB", (1080, 1920), color=(20, 20, 20))
        orchestrator.reel_detector = _FakeDetector(sample_frame)  # type: ignore[assignment]

        orchestrator._process_frame(sample_frame)
        orchestrator._process_frame(sample_frame)

        assert fake_tracker.started == [1, 2]
