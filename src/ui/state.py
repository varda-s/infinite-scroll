"""Reactive state management for the UI."""

import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional, Any

from src.capture.base import DeviceInfo


@dataclass
class ReelUpdate:
    """Information about a single reel."""

    reel_number: int
    duration_seconds: float
    screenshot_path: Optional[str] = None
    ascii_art: Optional[str] = None


@dataclass
class AppState:
    """Application state container."""

    # Device state
    connected_device: Optional[DeviceInfo] = None
    device_polling: bool = True

    # Printer state
    printer_type: str = "mock"  # "mock" or "rongta"
    printer_connected: bool = False

    # Session state
    session_active: bool = False
    session_id: Optional[int] = None
    current_reel_number: int = 0
    current_reel_duration: float = 0.0
    total_reels: int = 0
    total_time_seconds: float = 0.0
    session_start_time: Optional[datetime] = None

    # Live receipt content (for mock printer)
    live_receipt_lines: list[str] = field(default_factory=list)

    # External process management
    uxplay_process: Optional[Any] = None  # subprocess.Popen handle

    # UI callbacks
    _update_callbacks: list[Callable[[], None]] = field(default_factory=list)

    def add_update_callback(self, callback: Callable[[], None]) -> None:
        """Register a callback to be called when state changes."""
        self._update_callbacks.append(callback)

    def notify_update(self) -> None:
        """Notify all registered callbacks of a state change."""
        for callback in self._update_callbacks:
            try:
                callback()
            except Exception:
                pass

    def set_device(self, device: Optional[DeviceInfo]) -> None:
        """Update the connected device."""
        self.connected_device = device
        self.notify_update()

    def set_printer_type(self, printer_type: str) -> None:
        """Update the printer type."""
        self.printer_type = printer_type
        self.notify_update()

    def start_session(self, session_id: int) -> None:
        """Start a new tracking session."""
        self.session_active = True
        self.session_id = session_id
        self.current_reel_number = 0
        self.current_reel_duration = 0.0
        self.total_reels = 0
        self.total_time_seconds = 0.0
        self.session_start_time = datetime.now()
        self.live_receipt_lines = []
        self.notify_update()

    def update_reel(self, reel: ReelUpdate) -> None:
        """Update with new reel information."""
        self.current_reel_number = reel.reel_number
        self.current_reel_duration = reel.duration_seconds
        self.total_reels = reel.reel_number
        self.total_time_seconds += reel.duration_seconds
        self.notify_update()

    def add_receipt_line(self, line: str) -> None:
        """Add a line to the live receipt."""
        self.live_receipt_lines.append(line)
        self.notify_update()

    def add_receipt_lines(self, lines: list[str]) -> None:
        """Add multiple lines to the live receipt."""
        self.live_receipt_lines.extend(lines)
        self.notify_update()

    def end_session(self) -> None:
        """End the current session."""
        self.session_active = False
        self.notify_update()

    def reset(self) -> None:
        """Reset all session state."""
        self.session_active = False
        self.session_id = None
        self.current_reel_number = 0
        self.current_reel_duration = 0.0
        self.total_reels = 0
        self.total_time_seconds = 0.0
        self.session_start_time = None
        self.live_receipt_lines = []
        self.notify_update()


# Global state instance
app_state = AppState()
