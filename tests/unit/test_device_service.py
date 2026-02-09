"""Tests for device polling service behavior."""

import asyncio
from unittest.mock import MagicMock, patch

from src.capture.base import DeviceInfo, DeviceType
from src.ui.services.device_service import DeviceService
from src.ui.state import app_state


def test_poll_devices_does_not_switch_device_mid_session() -> None:
    """Active session should lock current mirror device selection."""
    service = DeviceService()
    current = DeviceInfo(
        device_type=DeviceType.IOS,
        device_id="mirror:uxplay:ReelTrackerA",
        device_name="ReelTracker A",
        model="uxplay",
        connection_type="mirror",
    )
    incoming = DeviceInfo(
        device_type=DeviceType.IOS,
        device_id="mirror:uxplay:ReelTrackerB",
        device_name="ReelTracker B",
        model="uxplay",
        connection_type="mirror",
    )
    app_state.set_device(current)
    app_state.session_active = True

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        with patch("src.ui.services.device_service.DeviceDetector.get_preferred_device", return_value=incoming):
            loop.run_until_complete(service._poll_devices())
        assert app_state.connected_device == current
    finally:
        app_state.session_active = False
        loop.close()


def test_try_auto_launch_sets_pairing_pin() -> None:
    """Auto-launch should store uxplay process and pairing code in state."""
    service = DeviceService()
    app_state.uxplay_process = None
    app_state.uxplay_pairing_code = None

    fake_proc = MagicMock()
    with patch("src.ui.services.device_service.MirrorLauncher.is_uxplay_available", return_value=True), \
         patch("src.ui.services.device_service.MirrorLauncher.launch_uxplay_with_pin", return_value=(fake_proc, "1234")):
        service._try_auto_launch_mirror()

    assert app_state.uxplay_process is fake_proc
    assert app_state.uxplay_pairing_code == "1234"


def test_stop_uxplay_clears_state() -> None:
    """Stopping uxplay should terminate process and clear pairing state."""
    service = DeviceService()
    proc = MagicMock()
    app_state.uxplay_process = proc
    app_state.uxplay_pairing_code = "5678"

    service._stop_uxplay()

    proc.terminate.assert_called_once()
    assert app_state.uxplay_process is None
    assert app_state.uxplay_pairing_code is None


def test_start_raises_if_pairing_not_ready() -> None:
    """Service startup should fail-fast when uxplay pairing cannot be initialized."""
    service = DeviceService()
    app_state.uxplay_process = None
    app_state.uxplay_pairing_code = None

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        with patch.object(service, "_try_auto_launch_mirror", return_value=None):
            try:
                loop.run_until_complete(service.start())
                raised = False
            except RuntimeError:
                raised = True
        assert raised is True
    finally:
        loop.close()


def test_poll_devices_rotates_pairing_after_sustained_disconnect() -> None:
    """After several missing polls, service should clear device and rotate PIN."""
    service = DeviceService(auto_launch_mirror=True)
    app_state.set_device(
        DeviceInfo(
            device_type=DeviceType.IOS,
            device_id="mirror:uxplay:ReelTracker",
            device_name="ReelTracker",
            model="uxplay",
            connection_type="mirror",
        )
    )
    app_state.session_active = False

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        with patch("src.ui.services.device_service.DeviceDetector.get_preferred_device", return_value=None), \
             patch.object(service, "restart_pairing_for_new_session", return_value=True) as rotate:
            loop.run_until_complete(service._poll_devices())
            loop.run_until_complete(service._poll_devices())
            loop.run_until_complete(service._poll_devices())

        assert app_state.connected_device is None
        assert rotate.call_count == 1
    finally:
        loop.close()
