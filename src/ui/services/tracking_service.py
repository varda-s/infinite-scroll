"""Tracking service for integrating the orchestrator with the UI."""

import asyncio
import threading
from pathlib import Path
from typing import Optional

from src.capture.base import BaseCapture, DeviceInfo, DeviceType
from src.capture.mock_capture import MockCapture
from src.capture.mirror_capture import MirrorCapture, MirrorDetector
from src.config import Config
from src.orchestrator import Orchestrator
from src.printing.base import BasePrinter
from src.printing.mock_printer import MockPrinter
from src.tracking.time_tracker import ReelSession
from src.ui.database.repository import ConfigRepository, SessionRepository
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
        self._running = False
        self._db_session_id: Optional[int] = None

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
        if self._running:
            return False

        device = app_state.connected_device
        if device is None:
            return False

        # Create capture based on device type and connection type
        capture = self._create_capture(device)
        if capture is None:
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

        # Update app state
        app_state.start_session(db_session.id)

        # Create orchestrator with callbacks
        self._orchestrator = Orchestrator(
            capture=capture,
            printer=printer,
            config=config,
            on_reel_change=self._on_reel_change,
            on_session_start=self._on_session_start,
            on_session_end=self._on_session_end,
        )

        # Start in background thread
        self._running = True
        self._thread = threading.Thread(target=self._run_orchestrator, daemon=True)
        self._thread.start()

        return True

    def stop_session(self) -> None:
        """Stop the current tracking session."""
        if not self._running or self._orchestrator is None:
            return

        self._orchestrator.stop()
        self._running = False

        if self._thread:
            self._thread.join(timeout=5.0)
            self._thread = None

    def _create_config(self) -> Config:
        """Create config from database settings."""
        return Config(
            capture_fps=ConfigRepository.get_typed("capture_fps") or 10,
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

            # iPhone mirror device (QuickTime, etc.)
            mirrors = MirrorDetector.detect_mirror_windows()
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
        output_dir = Path("output")
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
            app_state.end_session()

    def _on_reel_change(self, session: ReelSession) -> None:
        """Handle reel change event."""
        # Update app state
        reel_update = ReelUpdate(
            reel_number=session.reel_number,
            duration_seconds=session.duration,
            screenshot_path=None,
        )
        app_state.update_reel(reel_update)

        # Save to database
        if self._db_session_id:
            SessionRepository.add_receipt(
                session_id=self._db_session_id,
                reel_number=session.reel_number,
                duration_seconds=session.duration,
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

        self._db_session_id = None
        app_state.end_session()

    def _on_receipt_line(self, line: str) -> None:
        """Handle new receipt line from mock printer."""
        app_state.add_receipt_line(line)


# Singleton instance
tracking_service = TrackingService()
