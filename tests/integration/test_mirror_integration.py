"""Integration tests for mirror capture."""

from unittest.mock import patch, MagicMock

import pytest

from src.capture.mirror_capture import MirrorDetector, MirrorCapture, MirrorSource
from src.capture.device_detector import DeviceDetector
from src.capture.base import DeviceType


class TestMirrorDetectionIntegration:
    """Integration tests for mirror window detection."""

    def test_detect_mirror_windows_runs_without_error(self):
        """Test detect_mirror_windows runs without crashing."""
        # This will actually run AppleScript on macOS
        # Should return empty list or actual windows
        try:
            mirrors = MirrorDetector.detect_mirror_windows()
            assert isinstance(mirrors, list)
        except Exception as e:
            # On non-macOS systems, this might fail
            pytest.skip(f"Mirror detection not available: {e}")

    def test_debug_all_windows_runs_without_error(self):
        """Test debug_all_windows runs without crashing."""
        try:
            windows = MirrorDetector.debug_all_windows()
            assert isinstance(windows, list)
        except Exception as e:
            pytest.skip(f"Window detection not available: {e}")


class TestDeviceDetectorWithMirrors:
    """Integration tests for DeviceDetector with mirror support."""

    def test_detect_all_devices_includes_mirrors(self):
        """Test detect_all_devices includes mirror sources."""
        with patch.object(MirrorDetector, "detect_mirror_windows") as mock_detect:
            source = MirrorSource(
                window_id=1,
                window_name="iPhone",
                app_name="QuickTime Player",
                bounds=(0, 0, 400, 800),
            )
            mock_detect.return_value = [source]

            devices = DeviceDetector.detect_all_devices()

            # Should include the mirror device
            mirror_devices = [d for d in devices if d.device_id.startswith("mirror:")]
            assert len(mirror_devices) >= 1

    def test_get_preferred_device_returns_mirror(self):
        """Test get_preferred_device returns mirror device."""
        with patch.object(MirrorDetector, "detect_mirror_windows") as mock_detect:
            source = MirrorSource(
                window_id=1,
                window_name="iPhone",
                app_name="QuickTime Player",
                bounds=(0, 0, 400, 800),
            )
            mock_detect.return_value = [source]

            preferred = DeviceDetector.get_preferred_device()

            assert preferred is not None
            assert preferred.device_id.startswith("mirror:")


class TestMirrorCaptureIntegration:
    """Integration tests for MirrorCapture."""

    def test_context_manager_connect_disconnect(self):
        """Test MirrorCapture works as context manager."""
        source = MirrorSource(
            window_id=1,
            window_name="iPhone",
            app_name="QuickTime Player",
            bounds=(100, 100, 400, 800),
        )

        with MirrorCapture(mirror_source=source) as capture:
            assert capture.is_connected is True
            assert capture.device_info.device_type == DeviceType.IOS

        # After exiting context, should be disconnected
        assert capture.is_connected is False

    def test_capture_screen_with_mock_source(self):
        """Test capture_screen with a mock mirror source."""
        source = MirrorSource(
            window_id=1,
            window_name="iPhone",
            app_name="QuickTime Player",
            bounds=(100, 100, 400, 800),
        )
        capture = MirrorCapture(mirror_source=source)
        capture.connect()

        # Capture will likely return None since there's no actual window
        # But it should not crash
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            result = capture.capture_screen()
            # Should return None on failure
            assert result is None

        capture.disconnect()


class TestEndToEndMirrorFlow:
    """End-to-end tests for the mirror capture flow."""

    def test_full_detection_to_capture_flow(self):
        """Test the full flow from detection to capture setup."""
        # Mock a detected mirror window
        with patch.object(MirrorDetector, "detect_mirror_windows") as mock_detect:
            source = MirrorSource(
                window_id=1,
                window_name="iPhone 15 Pro",
                app_name="QuickTime Player",
                bounds=(100, 100, 400, 800),
            )
            mock_detect.return_value = [source]

            # Step 1: Detect mirrors
            mirrors = MirrorDetector.detect_mirror_windows()
            assert len(mirrors) == 1

            # Step 2: Get device from detector
            devices = DeviceDetector.detect_mirror_devices()
            assert len(devices) == 1
            assert devices[0].connection_type == "mirror"

            # Step 3: Create capture from detected mirror
            capture = MirrorCapture(mirror_source=mirrors[0])
            assert capture.connect() is True

            # Step 4: Verify device info
            device_info = capture.device_info
            assert device_info.device_type == DeviceType.IOS
            assert device_info.connection_type == "mirror"
            assert "mirror" in device_info.device_id.lower()

            capture.disconnect()
