"""Unit tests for UI tracking service start/stop behavior."""

from dataclasses import dataclass
from unittest.mock import patch

from src.printing.escpos_printer import ESCPOSPrinter
from src.capture.base import BaseCapture, DeviceInfo, DeviceType, ForegroundApp
from src.ui.services.tracking_service import TrackingService
from src.ui.state import app_state, LiveReelReceipt


@dataclass
class _DbSession:
    id: int


class _DummyCapture(BaseCapture):
    def __init__(self, connect_ok: bool = True) -> None:
        self._connect_ok = connect_ok
        self._connected = False
        self._info = DeviceInfo(
            device_type=DeviceType.IOS,
            device_id="mirror:uxplay:ReelTracker",
            device_name="ReelTracker (Screen Mirror)",
            model="uxplay",
            connection_type="mirror",
        )

    @property
    def device_info(self) -> DeviceInfo:
        return self._info

    @property
    def is_connected(self) -> bool:
        return self._connected

    def connect(self) -> bool:
        self._connected = self._connect_ok
        return self._connect_ok

    def disconnect(self) -> None:
        self._connected = False

    def capture_screen(self):
        return None

    def get_foreground_app(self):
        return ForegroundApp(package_name="com.instagram.android", activity="reels")


class _FakeThread:
    def __init__(self, target=None, daemon=None):
        self.target = target
        self.daemon = daemon

    def start(self) -> None:
        # Keep deterministic unit tests by not starting background loops.
        return None

    def join(self, timeout=None) -> None:
        return None


class _DummyOrchestratorForStop:
    def stop(self) -> None:
        return None


def test_start_session_recovers_device_and_uses_manual_mode() -> None:
    """Start session should recover missing UI device state and run in manual mode."""
    service = TrackingService()
    app_state.reset()
    app_state.set_device(None)

    preferred = DeviceInfo(
        device_type=DeviceType.IOS,
        device_id="mirror:uxplay:ReelTracker",
        device_name="ReelTracker (Screen Mirror)",
        model="uxplay",
        connection_type="mirror",
    )
    capture = _DummyCapture(connect_ok=True)

    created_kwargs = {}

    class _DummyOrchestrator:
        def __init__(self, *args, **kwargs) -> None:
            created_kwargs.update(kwargs)

        def run(self) -> None:
            return None

        def stop(self) -> None:
            return None

    with patch("src.ui.services.tracking_service.DeviceDetector.get_preferred_device", return_value=preferred), \
         patch.object(TrackingService, "_create_capture", return_value=capture), \
         patch.object(TrackingService, "_create_printer"), \
         patch.object(TrackingService, "_create_config"), \
         patch("src.ui.services.tracking_service.SessionRepository.create_session", return_value=_DbSession(id=42)), \
         patch("src.ui.services.tracking_service.Orchestrator", _DummyOrchestrator), \
         patch("src.ui.services.tracking_service.threading.Thread", _FakeThread):
        assert service.start_session(user_id=None) is True
        assert service.is_running is True
        assert app_state.connected_device is not None
        assert app_state.current_reel_number == 1
        assert created_kwargs["manual_session_start"] is True
        assert created_kwargs["use_content_detection"] is False
        assert "on_live_progress" in created_kwargs


def test_start_session_fails_when_capture_cannot_connect() -> None:
    """Start session should fail cleanly if mirror capture cannot connect."""
    service = TrackingService()
    app_state.reset()
    app_state.set_device(
        DeviceInfo(
            device_type=DeviceType.IOS,
            device_id="mirror:uxplay:ReelTracker",
            device_name="ReelTracker (Screen Mirror)",
            model="uxplay",
            connection_type="mirror",
        )
    )
    capture = _DummyCapture(connect_ok=False)

    with patch("src.ui.services.tracking_service.DeviceDetector.get_preferred_device", return_value=app_state.connected_device), \
         patch.object(TrackingService, "_create_capture", return_value=capture):
        assert service.start_session(user_id=None) is False


def test_start_session_does_not_rotate_pairing_when_device_already_connected() -> None:
    """Kiosk start should keep an already paired mirror connected."""
    service = TrackingService()
    connected = DeviceInfo(
        device_type=DeviceType.IOS,
        device_id="mirror:uxplay:ReelTracker",
        device_name="ReelTracker (Screen Mirror)",
        model="uxplay",
        connection_type="mirror",
    )
    app_state.reset()
    app_state.set_device(connected)
    capture = _DummyCapture(connect_ok=True)

    class _DummyOrchestrator:
        def __init__(self, *args, **kwargs) -> None:
            pass
        def run(self) -> None:
            return None
        def stop(self) -> None:
            return None

    with patch("src.ui.services.tracking_service.device_service.restart_pairing_for_new_session") as rotate, \
         patch.object(TrackingService, "_create_capture", return_value=capture), \
         patch.object(TrackingService, "_create_printer"), \
         patch.object(TrackingService, "_create_config"), \
         patch("src.ui.services.tracking_service.SessionRepository.create_session", return_value=_DbSession(id=100)), \
         patch("src.ui.services.tracking_service.Orchestrator", _DummyOrchestrator), \
         patch("src.ui.services.tracking_service.threading.Thread", _FakeThread):
        assert service.start_session(user_id=None) is True

    rotate.assert_not_called()


def test_stop_session_stops_pairing() -> None:
    """Stopping session should immediately prime next user pairing."""
    service = TrackingService()
    app_state.start_session(99)
    app_state.live_reel_receipts.append(
        LiveReelReceipt(reel_number=1, duration_seconds=1.2, screenshot_path=None)
    )
    service._running = True
    service._accept_callbacks = True
    service._orchestrator = _DummyOrchestratorForStop()
    service._thread = _FakeThread()

    with patch("src.ui.services.tracking_service.device_service.prime_next_user_pairing") as prime_pairing:
        service.stop_session()

    prime_pairing.assert_called_once()
    assert app_state.session_active is False
    assert app_state.live_reel_receipts == []
    assert service._accept_callbacks is False


def test_live_progress_ignored_when_callbacks_disabled() -> None:
    """Late worker callbacks after stop should not mutate UI state."""
    service = TrackingService()
    app_state.start_session(77)
    before_reel = app_state.current_reel_number
    before_duration = app_state.current_reel_duration
    service._accept_callbacks = False

    service._on_live_progress(5, 2.5, 6.0)

    assert app_state.current_reel_number == before_reel
    assert app_state.current_reel_duration == before_duration


def test_can_connect_matches_constructor_probe_without_open() -> None:
    """USB detection should succeed when Usb construction works."""
    closed = []

    class _FakeUsb:
        def __init__(self, vendor_id: int, product_id: int) -> None:
            self.vendor_id = vendor_id
            self.product_id = product_id

        def close(self) -> None:
            closed.append((self.vendor_id, self.product_id))

    with patch("escpos.printer.Usb", _FakeUsb):
        assert ESCPOSPrinter.can_connect() is True

    assert closed == [ESCPOSPrinter.RONGTA_USB_IDS[0]]
