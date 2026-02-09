"""Tests for uxplay launcher arguments."""

from unittest.mock import MagicMock, patch

from src.capture.mirror_launcher import MirrorLauncher


def test_launch_uxplay_with_pin_uses_pin_flag() -> None:
    """Launcher should require PIN-based access."""
    fake_proc = MagicMock()
    fake_proc.poll.return_value = None

    with patch.object(MirrorLauncher, "is_uxplay_available", return_value=True), \
         patch("src.capture.mirror_launcher.subprocess.run"), \
         patch("src.capture.mirror_launcher.subprocess.Popen", return_value=fake_proc) as popen, \
         patch("src.capture.mirror_launcher.time.sleep"):
        proc, pin = MirrorLauncher.launch_uxplay_with_pin(pin="1234")

    assert proc is fake_proc
    assert pin == "1234"
    args = popen.call_args[0][0]
    assert "-pin" in args
    assert "1234" in args
    assert "-pw" not in args
