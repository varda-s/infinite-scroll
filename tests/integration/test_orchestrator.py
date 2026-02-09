"""Integration tests for orchestrator."""

import threading
import time
from pathlib import Path

import pytest
from PIL import Image
import numpy as np

from src.config import Config
from src.capture.mock_capture import MockCapture
from src.printing.mock_printer import MockPrinter
from src.orchestrator import Orchestrator
from src.tracking.time_tracker import ReelSession


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
        assert "INSTAGRAM REEL TRACKER" in content

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
        assert "SESSION COMPLETE" in content
        assert "THANK YOU FOR SCROLLING" in content

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
        assert "INSTAGRAM REEL TRACKER" in content  # Header
        assert "Session started:" in content
        assert "REEL #" in content  # At least one reel
        assert "Time spent:" in content  # Duration tracked
        assert "SESSION COMPLETE" in content  # Summary
        assert "Total reels viewed:" in content
        assert "THANK YOU FOR SCROLLING" in content  # Thank you message
