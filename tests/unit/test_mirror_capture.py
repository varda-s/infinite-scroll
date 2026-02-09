"""Unit tests for mirror capture and detection."""

import subprocess
from unittest.mock import patch, MagicMock

import pytest

from src.capture.mirror_capture import (
    MirrorSource,
    MirrorDetector,
    MirrorCapture,
    get_available_mirrors,
)
from src.capture.base import DeviceType, DeviceInfo


class TestMirrorSource:
    """Tests for the MirrorSource dataclass."""

    def test_create_mirror_source(self):
        """Test creating a MirrorSource."""
        source = MirrorSource(
            window_id=123,
            window_name="iPhone 15 Pro",
            app_name="QuickTime Player",
            bounds=(0, 0, 400, 800),
        )

        assert source.window_id == 123
        assert source.window_name == "iPhone 15 Pro"
        assert source.app_name == "QuickTime Player"
        assert source.bounds == (0, 0, 400, 800)


class TestMirrorDetector:
    """Tests for the MirrorDetector class."""

    def test_mirror_apps_contains_known_apps(self):
        """Test MIRROR_APPS contains expected iOS apps."""
        apps = MirrorDetector.MIRROR_APPS

        assert "iPhone Mirroring" in apps
        assert "QuickTime Player" in apps
        assert "Reflector" in apps
        assert "uxplay" in apps

    def test_iphone_mirroring_is_first_priority(self):
        """Test iPhone Mirroring is checked first (highest priority)."""
        apps = MirrorDetector.MIRROR_APPS

        assert apps[0] == "iPhone Mirroring"
        assert apps[1] == "QuickTime Player"

    def test_phone_keywords_exists(self):
        """Test PHONE_KEYWORDS contains expected keywords."""
        keywords = MirrorDetector.PHONE_KEYWORDS

        assert "iphone" in keywords
        assert "ipad" in keywords

    @patch("subprocess.run")
    def test_detect_mirror_windows_empty_when_no_windows(self, mock_run):
        """Test detect_mirror_windows returns empty list when no windows."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="",
        )

        mirrors = MirrorDetector.detect_mirror_windows()

        assert mirrors == []

    @patch("subprocess.run")
    def test_detect_mirror_windows_finds_iphone_mirroring(self, mock_run):
        """Test detect_mirror_windows finds iPhone Mirroring window first."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="iPhone 15|100|200|400|800",
        )

        mirrors = MirrorDetector.detect_mirror_windows()

        assert len(mirrors) == 1
        # iPhone Mirroring is checked first (priority)
        assert mirrors[0].app_name == "iPhone Mirroring"
        assert mirrors[0].window_name == "iPhone 15"

    @patch("subprocess.run")
    def test_detect_mirror_windows_falls_back_to_quicktime(self, mock_run):
        """Test detect_mirror_windows falls back to QuickTime when iPhone Mirroring not found."""
        # First call (iPhone Mirroring) returns empty, second call (QuickTime) returns window
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=""),  # iPhone Mirroring not found
            MagicMock(returncode=0, stdout="iPhone 15|100|200|400|800"),  # QuickTime found
        ]

        mirrors = MirrorDetector.detect_mirror_windows()

        assert len(mirrors) == 1
        assert mirrors[0].app_name == "QuickTime Player"
        assert mirrors[0].window_name == "iPhone 15"

    @patch("subprocess.run")
    def test_detect_mirror_windows_handles_timeout(self, mock_run):
        """Test detect_mirror_windows handles subprocess timeout."""
        mock_run.side_effect = subprocess.TimeoutExpired("osascript", 5)

        mirrors = MirrorDetector.detect_mirror_windows()

        assert mirrors == []

    @patch("subprocess.run")
    def test_detect_mirror_windows_handles_error(self, mock_run):
        """Test detect_mirror_windows handles subprocess error."""
        mock_run.return_value = MagicMock(returncode=1, stdout="")

        mirrors = MirrorDetector.detect_mirror_windows()

        assert mirrors == []

    def test_parse_applescript_list_empty(self):
        """Test parsing empty AppleScript output."""
        result = MirrorDetector._parse_applescript_list("")

        assert result == []

    def test_parse_applescript_list_single_entry(self):
        """Test parsing single entry."""
        output = '{QuickTime Player, iPhone, 0, 0, 400, 800}'
        result = MirrorDetector._parse_applescript_list(output)

        assert len(result) == 1
        assert result[0][0] == "QuickTime Player"
        assert result[0][1] == "iPhone"

    def test_parse_applescript_list_multiple_entries(self):
        """Test parsing multiple entries."""
        output = '{{App1, Win1, 0, 0, 100, 100}, {App2, Win2, 0, 0, 200, 200}}'
        result = MirrorDetector._parse_applescript_list(output)

        assert len(result) == 2

    @patch("subprocess.run")
    def test_debug_all_windows_returns_list(self, mock_run):
        """Test debug_all_windows returns a list of window info."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Safari|Google\nQuickTime Player|iPhone",
        )

        windows = MirrorDetector.debug_all_windows()

        assert isinstance(windows, list)


class TestMirrorCapture:
    """Tests for the MirrorCapture class."""

    def test_init_without_source(self):
        """Test initializing without a mirror source."""
        capture = MirrorCapture()

        assert capture._mirror_source is None
        assert capture._connected is False

    def test_init_with_source(self):
        """Test initializing with a mirror source."""
        source = MirrorSource(
            window_id=1,
            window_name="iPhone",
            app_name="QuickTime Player",
            bounds=(0, 0, 400, 800),
        )
        capture = MirrorCapture(mirror_source=source)

        assert capture._mirror_source == source

    def test_device_info_raises_when_not_connected(self):
        """Test device_info raises error when not connected."""
        capture = MirrorCapture()

        with pytest.raises(RuntimeError, match="Not connected"):
            _ = capture.device_info

    def test_is_connected_false_initially(self):
        """Test is_connected is False initially."""
        capture = MirrorCapture()

        assert capture.is_connected is False

    @patch.object(MirrorDetector, "detect_mirror_windows")
    def test_connect_fails_when_no_mirrors(self, mock_detect):
        """Test connect returns False when no mirrors detected."""
        mock_detect.return_value = []
        capture = MirrorCapture()

        result = capture.connect()

        assert result is False
        assert capture.is_connected is False

    @patch.object(MirrorDetector, "detect_mirror_windows")
    def test_connect_succeeds_with_auto_detect(self, mock_detect):
        """Test connect succeeds with auto-detection."""
        source = MirrorSource(
            window_id=1,
            window_name="iPhone",
            app_name="QuickTime Player",
            bounds=(0, 0, 400, 800),
        )
        mock_detect.return_value = [source]
        capture = MirrorCapture()

        result = capture.connect()

        assert result is True
        assert capture.is_connected is True
        assert capture.device_info.device_type == DeviceType.IOS

    def test_connect_succeeds_with_provided_source(self):
        """Test connect succeeds with provided source."""
        source = MirrorSource(
            window_id=1,
            window_name="iPhone",
            app_name="QuickTime Player",
            bounds=(0, 0, 400, 800),
        )
        capture = MirrorCapture(mirror_source=source)

        result = capture.connect()

        assert result is True
        assert capture.is_connected is True
        assert capture.device_info.device_type == DeviceType.IOS

    def test_connect_sets_connection_type_to_mirror(self):
        """Test connect sets connection_type to mirror."""
        source = MirrorSource(
            window_id=1,
            window_name="iPhone",
            app_name="QuickTime Player",
            bounds=(0, 0, 400, 800),
        )
        capture = MirrorCapture(mirror_source=source)
        capture.connect()

        assert capture.device_info.connection_type == "mirror"

    def test_disconnect_clears_state(self):
        """Test disconnect clears state."""
        source = MirrorSource(
            window_id=1,
            window_name="iPhone",
            app_name="QuickTime Player",
            bounds=(0, 0, 400, 800),
        )
        capture = MirrorCapture(mirror_source=source)
        capture.connect()

        capture.disconnect()

        assert capture.is_connected is False
        assert capture._mirror_source is None

    def test_capture_screen_returns_none_when_not_connected(self):
        """Test capture_screen returns None when not connected."""
        capture = MirrorCapture()

        result = capture.capture_screen()

        assert result is None

    def test_get_foreground_app_returns_instagram(self):
        """Test get_foreground_app returns Instagram for mirror mode."""
        source = MirrorSource(
            window_id=1,
            window_name="iPhone",
            app_name="QuickTime Player",
            bounds=(0, 0, 400, 800),
        )
        capture = MirrorCapture(mirror_source=source)
        capture.connect()

        app = capture.get_foreground_app()

        assert app is not None
        assert "instagram" in app.package_name.lower()


class TestGetAvailableMirrors:
    """Tests for the get_available_mirrors function."""

    @patch.object(MirrorDetector, "detect_mirror_windows")
    def test_returns_detected_mirrors(self, mock_detect):
        """Test returns list of detected mirrors."""
        source = MirrorSource(
            window_id=1,
            window_name="iPhone",
            app_name="QuickTime Player",
            bounds=(0, 0, 400, 800),
        )
        mock_detect.return_value = [source]

        mirrors = get_available_mirrors()

        assert mirrors == [source]
