"""Unit tests for device detector."""

from unittest.mock import patch

from src.capture.device_detector import DeviceDetector
from src.capture.base import DeviceType, DeviceInfo


class TestDetectMirrorDevices:
    """Tests for DeviceDetector.detect_mirror_devices()."""

    def test_detect_ios_mirror(self):
        """Test detecting ReelTracker uxplay mirror device."""
        from src.capture.mirror_capture import MirrorSource, MirrorDetector

        mock_source = MirrorSource(
            window_id=1,
            window_name="ReelTracker",
            app_name="uxplay",
            bounds=(0, 0, 400, 800),
        )

        with patch.object(MirrorDetector, "detect_reeldetector_windows", return_value=[mock_source]), \
             patch.object(MirrorDetector, "is_stream_active", return_value=True):
            devices = DeviceDetector.detect_mirror_devices()

            assert len(devices) == 1
            assert devices[0].device_type == DeviceType.IOS
            assert devices[0].device_id == "mirror:uxplay:ReelTracker"
            assert "(Screen Mirror)" in devices[0].device_name
            assert devices[0].connection_type == "mirror"

    def test_detect_multiple_mirrors(self):
        """Test detecting multiple mirror devices."""
        from src.capture.mirror_capture import MirrorSource, MirrorDetector

        sources = [
            MirrorSource(
                window_id=1,
                window_name="ReelTracker",
                app_name="uxplay",
                bounds=(0, 0, 400, 800),
            ),
            MirrorSource(
                window_id=2,
                window_name="ReelTracker Alt",
                app_name="GStreamer",
                bounds=(500, 0, 600, 800),
            ),
        ]

        with patch.object(MirrorDetector, "detect_reeldetector_windows", return_value=sources), \
             patch.object(MirrorDetector, "is_stream_active", return_value=True):
            devices = DeviceDetector.detect_mirror_devices()

            assert len(devices) == 2

    def test_handles_exception(self):
        """Test handles MirrorDetector exception gracefully."""
        from src.capture.mirror_capture import MirrorDetector

        with patch.object(MirrorDetector, "detect_reeldetector_windows", side_effect=Exception("Error")):
            devices = DeviceDetector.detect_mirror_devices()

            assert len(devices) == 0

    def test_filters_inactive_mirror_streams(self):
        """Test inactive mirror windows are not reported as connected devices."""
        from src.capture.mirror_capture import MirrorSource, MirrorDetector

        mock_source = MirrorSource(
            window_id=1,
            window_name="ReelTracker",
            app_name="uxplay",
            bounds=(0, 0, 400, 800),
        )

        with patch.object(MirrorDetector, "detect_reeldetector_windows", return_value=[mock_source]), \
             patch.object(MirrorDetector, "is_stream_active", return_value=False):
            devices = DeviceDetector.detect_mirror_devices()

            assert devices == []

    def test_rejects_non_reeldetector_mirror_apps(self):
        """Test iPhone Mirroring/QuickTime style sources are ignored."""
        from src.capture.mirror_capture import MirrorSource, MirrorDetector

        iphone_source = MirrorSource(
            window_id=1,
            window_name="iPhone 15",
            app_name="iPhone Mirroring",
            bounds=(0, 0, 400, 800),
        )

        with patch.object(MirrorDetector, "detect_reeldetector_windows", return_value=[]), \
             patch.object(MirrorDetector, "detect_mirror_windows", return_value=[iphone_source]):
            devices = DeviceDetector.detect_mirror_devices()
            assert devices == []


class TestDetectAllDevices:
    """Tests for DeviceDetector.detect_all_devices()."""

    def test_returns_mirror_devices(self):
        """Test returns mirror devices."""
        mirror_device = DeviceInfo(
            device_type=DeviceType.IOS,
            device_id="mirror:uxplay:ReelTracker",
            device_name="ReelTracker (Mirror)",
            connection_type="mirror",
        )

        with patch.object(DeviceDetector, "detect_mirror_devices", return_value=[mirror_device]):
            devices = DeviceDetector.detect_all_devices()

            assert len(devices) == 1
            assert devices[0].device_id == "mirror:uxplay:ReelTracker"


class TestGetPreferredDevice:
    """Tests for DeviceDetector.get_preferred_device()."""

    def test_returns_first_mirror(self):
        """Test returns first mirror device."""
        mirror_device = DeviceInfo(
            device_type=DeviceType.IOS,
            device_id="mirror:uxplay:ReelTracker",
            device_name="ReelTracker (Mirror)",
            connection_type="mirror",
        )

        with patch.object(DeviceDetector, "detect_all_devices", return_value=[mirror_device]):
            preferred = DeviceDetector.get_preferred_device()

            assert preferred.device_id == "mirror:uxplay:ReelTracker"

    def test_returns_none_when_no_devices(self):
        """Test returns None when no devices available."""
        with patch.object(DeviceDetector, "detect_all_devices", return_value=[]):
            preferred = DeviceDetector.get_preferred_device()

            assert preferred is None

    def test_prefers_first_device(self):
        """Test prefers first device when multiple exist."""
        devices = [
            DeviceInfo(
                device_type=DeviceType.IOS,
                device_id="mirror:uxplay:ReelTracker1",
                device_name="ReelTracker 1 (Mirror)",
                connection_type="mirror",
            ),
            DeviceInfo(
                device_type=DeviceType.IOS,
                device_id="mirror:uxplay:ReelTracker2",
                device_name="ReelTracker 2 (Mirror)",
                connection_type="mirror",
            ),
        ]

        with patch.object(DeviceDetector, "detect_all_devices", return_value=devices):
            preferred = DeviceDetector.get_preferred_device()

            assert preferred.device_id == "mirror:uxplay:ReelTracker1"
