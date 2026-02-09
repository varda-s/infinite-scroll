"""Tracking service for integrating the orchestrator with the UI."""

import asyncio
import threading
import time
from pathlib import Path
from typing import Optional

from PIL import Image

from src.capture.base import BaseCapture, DeviceInfo, DeviceType
from src.capture.device_detector import DeviceDetector
from src.capture.mock_capture import MockCapture
from src.capture.mirror_capture import MirrorCapture, MirrorDetector
from src.config import Config
from src.detection.image_utils import compute_phash, extract_center_region
from src.orchestrator import Orchestrator
from src.printing.base import BasePrinter
from src.printing.mock_printer import MockPrinter
from src.tracking.time_tracker import ReelSession
from src.ui.database.repository import ConfigRepository, SessionRepository
from src.ui.services.device_service import device_service
from src.ui.services.media_paths import OUTPUT_ROOT
from src.ui.services.replay_service import ensure_session_replay_video
from src.ui.state import app_state, ReelUpdate


class UIAwareMockPrinter(MockPrinter):
    """Mock printer that also updates the UI state."""

    def __init__(self, output_dir: Path, verbose: bool = False) -> None:
        super().__init__(output_dir, verbose)
        self._line_callback: Optional[callable] = None

    def set_line_callback(self, callback: callable) -> None:
        """Set callback for when lines are added."""
        self._line_callback = callback

    def _add_receipt_line(self, line: str) -> None:
        """Add line to receipt and notify UI."""
        super()._add_receipt_line(line)
        if self._line_callback:
            try:
                self._line_callback(line)
            except Exception:
                pass


class TrackingService:
    """Service for managing tracking sessions from the UI."""

    def __init__(self):
        self._orchestrator: Optional[Orchestrator] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_thread: Optional[threading.Thread] = None
        self._running = False
        self._stop_in_progress = False
        self._accept_callbacks = False
        self._db_session_id: Optional[int] = None
        self._session_output_dir: Optional[Path] = None
        self._last_reel_hash: Optional[str] = None
        self._last_reel_at: float = 0.0

    @property
    def is_running(self) -> bool:
        """Check if a session is running."""
        return self._running

    def start_session(self, user_id: int = None) -> bool:
        """Start a tracking session.

        Args:
            user_id: Database ID of the user starting the session.

        Returns:
            True if session started successfully.
        """
        if self._running or self._stop_in_progress:
            return False

        # Kiosk flow: if a mirror is already connected, use it directly.
        # Do not rotate pairing here because that would drop an active mirror and
        # force users to reconnect unnecessarily.
        device: DeviceInfo | None = app_state.connected_device
        if device is None:
            # No UI device cached; poll briefly to pick up an already mirrored phone.
            for _ in range(20):  # up to ~10s
                device = DeviceDetector.get_preferred_device()
                if device is not None:
                    break
                time.sleep(0.5)
            if device is None:
                return False
            app_state.set_device(device)

        # Create capture based on device type and connection type.
        # Mirror detection can briefly flap; retry for a short window.
        capture = self._create_capture_with_retry(device, timeout_seconds=6.0)
        if capture is None:
            return False

        # Validate capture connectivity before mutating app/database state.
        if not capture.connect():
            return False

        # Create printer
        printer = self._create_printer()

        # Create config from database settings
        config = self._create_config()

        # Create database session
        db_session = SessionRepository.create_session(
            device_type=device.device_type.name.lower(),
            device_name=device.device_name,
            printer_type=app_state.printer_type,
            user_id=user_id,
        )
        self._db_session_id = db_session.id
        self._session_output_dir = OUTPUT_ROOT / "sessions" / f"session_{db_session.id}"
        self._session_output_dir.mkdir(parents=True, exist_ok=True)

        # Update app state
        app_state.start_session(db_session.id)
        self._last_reel_hash = None
        self._last_reel_at = 0.0

        # Create orchestrator with callbacks
        self._orchestrator = Orchestrator(
            capture=capture,
            printer=printer,
            config=config,
            on_reel_change=self._on_reel_change,
            on_session_start=self._on_session_start,
            on_session_end=self._on_session_end,
            on_live_progress=self._on_live_progress,
            use_content_detection=False,
            manual_session_start=True,
        )

        # Start in background thread
        self._running = True
        self._accept_callbacks = True
        self._thread = threading.Thread(target=self._run_orchestrator, daemon=True)
        self._thread.start()

        return True

    def _create_capture_with_retry(
        self, device: DeviceInfo, timeout_seconds: float = 6.0
    ) -> Optional[BaseCapture]:
        """Create capture with a short retry window for flaky mirror discovery."""
        deadline = time.time() + timeout_seconds
        capture = self._create_capture(device)
        while capture is None and time.time() < deadline:
            time.sleep(0.25)
            # Re-poll in case the cached device is stale.
            refreshed = DeviceDetector.get_preferred_device()
            if refreshed is not None:
                app_state.set_device(refreshed)
                device = refreshed
            capture = self._create_capture(device)
        return capture

    def stop_session(self) -> None:
        """Stop the current tracking session."""
        if self._stop_in_progress:
            return
        if not self._running and self._orchestrator is None:
            return

        # Stop accepting async callbacks immediately and clear UI now.
        self._accept_callbacks = False
        self._running = False
        self._stop_in_progress = True
        app_state.end_session()
        app_state.set_device(None)
        self._last_reel_hash = None
        self._last_reel_at = 0.0

        orchestrator = self._orchestrator
        worker = self._thread
        self._orchestrator = None
        self._thread = None

        def _finalize_stop() -> None:
            try:
                if orchestrator is not None:
                    orchestrator.stop()
                if worker is not None:
                    worker.join(timeout=5.0)
                device_service.prime_next_user_pairing()
            finally:
                self._stop_in_progress = False

        self._stop_thread = threading.Thread(target=_finalize_stop, daemon=True)
        self._stop_thread.start()

    def _create_config(self) -> Config:
        """Create config from database settings."""
        configured_fps = ConfigRepository.get_typed("capture_fps")
        if not isinstance(configured_fps, int) or configured_fps < 15:
            configured_fps = 20

        return Config(
            capture_fps=configured_fps,
            capture_timeout=ConfigRepository.get_typed("capture_timeout") or 5.0,
            hash_threshold=ConfigRepository.get_typed("hash_threshold") or 15,
            min_reel_duration=ConfigRepository.get_typed("min_reel_duration") or 0.5,
            printer_width=ConfigRepository.get_typed("printer_width") or 384,
            save_screenshots=ConfigRepository.get_typed("save_screenshots") or True,
        )

    def _create_capture(self, device: DeviceInfo) -> Optional[BaseCapture]:
        """Create capture instance based on device type."""
        try:
            # Mock device for testing
            if device.device_type == DeviceType.MOCK:
                return MockCapture()

            # ReelTracker booth mirror device (uxplay/GStreamer)
            mirrors = MirrorDetector.detect_reeldetector_windows()
            for mirror in mirrors:
                mirror_id = f"mirror:{mirror.app_name}:{mirror.window_name}"
                if mirror_id == device.device_id:
                    return MirrorCapture(mirror_source=mirror)

            # If no exact match, try first available mirror
            if mirrors:
                return MirrorCapture(mirror_source=mirrors[0])

            return None
        except Exception as e:
            print(f"Error creating capture: {e}")
            return None

    def _create_printer(self) -> BasePrinter:
        """Create printer instance based on selected type."""
        output_dir = OUTPUT_ROOT
        output_dir.mkdir(parents=True, exist_ok=True)

        if app_state.printer_type == "mock":
            printer = UIAwareMockPrinter(output_dir=output_dir, verbose=False)
            printer.set_line_callback(self._on_receipt_line)
            return printer
        else:
            # For Rongta, use the mock for now - can add real ESC/POS later
            from src.printing.escpos_printer import ESCPOSPrinter
            try:
                return ESCPOSPrinter()
            except Exception:
                # Fall back to mock if printer not available
                printer = UIAwareMockPrinter(output_dir=output_dir, verbose=False)
                printer.set_line_callback(self._on_receipt_line)
                return printer

    def _run_orchestrator(self) -> None:
        """Run orchestrator in background thread."""
        try:
            if self._orchestrator:
                self._orchestrator.run()
        except Exception as e:
            print(f"Orchestrator error: {e}")
        finally:
            self._running = False
            self._accept_callbacks = False
            device_service.prime_next_user_pairing()
            app_state.set_device(None)
            app_state.end_session()
            self._last_reel_hash = None
            self._last_reel_at = 0.0

    def _compute_reel_hash(self, screenshot: Optional[Image.Image]) -> Optional[str]:
        """Compute compact hash for deduplicating repeated reel snapshots."""
        if screenshot is None:
            return None
        try:
            center = extract_center_region(screenshot, width_ratio=0.62, height_ratio=0.62)
            return str(compute_phash(center, hash_size=8))
        except Exception:
            return None

    @staticmethod
    def _hash_distance(h1: Optional[str], h2: Optional[str]) -> int:
        """Return hamming distance between hash strings."""
        if not h1 or not h2:
            return 64
        try:
            from imagehash import hex_to_hash

            return int(hex_to_hash(h1) - hex_to_hash(h2))
        except Exception:
            return 64

    def _should_drop_duplicate_reel(self, session: ReelSession) -> bool:
        """Filter noisy duplicate reel callbacks from bursty detector transitions."""
        now = time.time()
        # Hard cooldown to prevent one swipe from generating multiple receipts.
        if self._last_reel_at and now - self._last_reel_at < 2.0:
            return True

        new_hash = self._compute_reel_hash(session.screenshot)
        if (
            self._last_reel_hash
            and new_hash
            and self._hash_distance(self._last_reel_hash, new_hash) <= 8
            and (now - self._last_reel_at) <= 8.0
        ):
            return True

        self._last_reel_at = now
        self._last_reel_hash = new_hash
        return False

    def _on_reel_change(self, session: ReelSession) -> None:
        """Handle reel change event."""
        if not self._accept_callbacks or not app_state.session_active:
            return
        if self._should_drop_duplicate_reel(session):
            return
        screenshot_path: Optional[str] = None
        if session.screenshot is not None and self._session_output_dir is not None:
            screenshot_file = self._session_output_dir / f"reel_{session.reel_number:04d}.png"
            try:
                session.screenshot.save(screenshot_file)
                screenshot_path = str(screenshot_file.resolve())
            except Exception:
                screenshot_path = None

        # Update app state
        reel_update = ReelUpdate(
            reel_number=session.reel_number,
            duration_seconds=session.duration,
            screenshot_path=screenshot_path,
        )
        app_state.on_reel_completed(reel_update)

        # Save to database
        if self._db_session_id:
            SessionRepository.add_receipt(
                session_id=self._db_session_id,
                reel_number=session.reel_number,
                duration_seconds=session.duration,
                screenshot_path=screenshot_path,
            )

    def _on_session_start(self) -> None:
        """Handle session start event."""
        pass  # State already updated in start_session

    def _on_session_end(self, total_reels: int, total_time: float, receipt: str) -> None:
        """Handle session end event."""
        # Update database
        if self._db_session_id:
            SessionRepository.complete_session(
                session_id=self._db_session_id,
                total_reels=total_reels,
                total_time_seconds=total_time,
                receipt_content=receipt,
            )
            ensure_session_replay_video(self._db_session_id)

        self._db_session_id = None
        self._session_output_dir = None
        self._accept_callbacks = False
        device_service.prime_next_user_pairing()
        app_state.set_device(None)
        app_state.end_session()

    def _on_live_progress(
        self, reel_number: int, duration_seconds: float, total_time_seconds: float
    ) -> None:
        """Handle real-time reel duration updates."""
        if not self._accept_callbacks or not app_state.session_active:
            return
        app_state.set_live_progress(reel_number, duration_seconds, total_time_seconds)

    def _on_receipt_line(self, line: str) -> None:
        """Handle new receipt line from mock printer."""
        app_state.add_receipt_line(line)


# Singleton instance
tracking_service = TrackingService()
