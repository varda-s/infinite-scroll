"""Main orchestrator for the Instagram Reel Tracker."""

import signal
import sys
import threading
from datetime import datetime
from time import sleep, time
from typing import Callable

from PIL import Image

from src.capture.base import BaseCapture
from src.config import Config
from src.detection.app_detector import AppDetector, AppState
from src.detection.content_detector import ContentDetector, ContentType
from src.detection.reel_detector import ReelDetector, ReelChangeType
from src.printing.base import BasePrinter
from src.tracking.time_tracker import TimeTracker, ReelSession


class Orchestrator:
    """Main processing loop for tracking Instagram reels."""

    def __init__(
        self,
        capture: BaseCapture,
        printer: BasePrinter,
        config: Config,
        on_reel_change: Callable[[ReelSession], None] | None = None,
        on_session_start: Callable[[], None] | None = None,
        on_session_end: Callable[[int, float, str], None] | None = None,
        on_live_progress: Callable[[int, float, float], None] | None = None,
        use_content_detection: bool = True,
        manual_session_start: bool = False,
    ) -> None:
        """Initialize orchestrator.

        Args:
            capture: Screen capture implementation.
            printer: Printer implementation.
            config: Application configuration.
            on_reel_change: Optional callback for reel changes.
            on_session_start: Optional callback when session starts.
            on_session_end: Optional callback when session ends (total_reels, total_time, receipt).
            on_live_progress: Optional callback for real-time reel timer updates
                (current_reel_number, current_reel_duration, total_time).
            use_content_detection: Use content-based session detection (for mirror mode).
            manual_session_start: Start a session immediately on run().
        """
        self.capture = capture
        self.printer = printer
        self.config = config
        self.on_reel_change = on_reel_change
        self.on_session_start = on_session_start
        self.on_session_end = on_session_end
        self.on_live_progress = on_live_progress
        self.use_content_detection = use_content_detection
        self.manual_session_start = manual_session_start

        self.app_detector = AppDetector(
            android_package=config.instagram_package,
            ios_bundle_id=config.instagram_bundle_id,
        )
        self.reel_detector = ReelDetector(
            hash_threshold=config.hash_threshold,
        )
        self.content_detector = ContentDetector(
            hash_threshold=config.hash_threshold,
        )
        self.time_tracker = TimeTracker(
            min_duration=config.min_reel_duration,
            on_reel_complete=self._on_reel_complete,
        )

        self._running = False
        self._session_start: datetime | None = None
        self._frame_count = 0
        self._last_app_state: AppState = AppState.NOT_RUNNING
        self._session_active = False  # True when user is in Reels mode
        self._capture_failure_count = 0
        self._max_capture_failures = 0

    def _on_reel_complete(self, session: ReelSession) -> None:
        """Handle completed reel viewing.

        Args:
            session: Completed reel session.
        """
        if session.screenshot:
            self.printer.print_reel(
                screenshot=session.screenshot,
                duration_seconds=session.duration,
                reel_number=session.reel_number,
                analysis_frames=session.analysis_frames,
            )

        if self.on_reel_change:
            self.on_reel_change(session)

    def _setup_signal_handlers(self) -> None:
        """Set up signal handlers for graceful shutdown.

        Only sets up handlers when running in the main thread.
        """
        # Signal handlers can only be set in the main thread
        if threading.current_thread() is not threading.main_thread():
            return

        def signal_handler(signum: int, frame: object) -> None:
            print("\nShutting down...")
            self._running = False

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    def _check_instagram_state(self) -> AppState:
        """Check if Instagram is running and in reels mode.

        Returns:
            Current app state.
        """
        foreground_app = self.capture.get_foreground_app()

        if foreground_app is None:
            return AppState.NOT_RUNNING

        if not self.app_detector.is_instagram_package(foreground_app.package_name):
            return AppState.NOT_RUNNING

        if self.app_detector.is_reels_activity(foreground_app.activity):
            return AppState.REELS_MODE

        return AppState.RUNNING_FOREGROUND

    def _process_frame(self, frame: Image.Image) -> None:
        """Process a single captured frame.

        Args:
            frame: Screenshot frame.
        """
        change_type = self.reel_detector.process_frame(frame)

        if change_type == ReelChangeType.NEW_REEL:
            # Use current in-progress reel to compute the next reel index.
            # `get_reel_count()` excludes the in-progress reel, which would
            # otherwise produce duplicate numbering (1, 1, 2, ...) on first swipes.
            if self.time_tracker.current_reel is not None:
                reel_count = self.time_tracker.current_reel.reel_number + 1
            else:
                reel_count = self.time_tracker.get_reel_count() + 1

            # Start tracking new reel
            screenshot = self.reel_detector.last_screenshot
            self.time_tracker.start_new_reel(
                reel_number=reel_count,
                screenshot=screenshot,
            )

        elif change_type == ReelChangeType.NONE and self.reel_detector.is_stable():
            # Update screenshot with stable frame
            screenshot = self.reel_detector.get_stable_screenshot()
            if screenshot:
                self.time_tracker.update_screenshot(screenshot)

        if self.on_live_progress and self.time_tracker.current_reel:
            self.on_live_progress(
                self.time_tracker.current_reel.reel_number,
                self.time_tracker.get_current_duration(),
                self.time_tracker.get_total_time(),
            )

    def run(self) -> None:
        """Run the main processing loop."""
        self._setup_signal_handlers()
        self._running = True
        self._session_start = None
        self._session_active = False
        self._frame_count = 0
        self._capture_failure_count = 0

        # Connect to device
        if not self.capture.is_connected:
            print("Connecting to device...")
            if not self.capture.connect():
                print("Failed to connect to device")
                return
        else:
            print("Using existing connected device...")

        device_info = self.capture.device_info
        print(f"Connected to: {device_info.device_name}")
        if device_info.model:
            print(f"  Model: {device_info.model}")
        if device_info.os_version:
            print(f"  OS: {device_info.os_version}")

        # Detect if we should use content-based detection
        # (for mirror mode where we can't detect foreground app)
        is_mirror_mode = device_info.connection_type == "mirror"
        use_content = self.use_content_detection and is_mirror_mode

        # Calculate frame interval
        frame_interval = 1.0 / self.config.capture_fps
        # Treat a sustained run of failed captures as mirror disconnect.
        self._max_capture_failures = max(6, int(self.config.capture_fps * 1.5))

        print(f"\nMonitoring at {self.config.capture_fps} FPS")
        if self.manual_session_start:
            print("Manual session mode enabled.")
            print("Session started via UI. Detecting reel changes from mirror feed.")
        elif use_content:
            print("Using content-based session detection (mirror mode)")
            print("Session will auto-start when Reels content is detected.")
        else:
            print("Waiting for Instagram Reels...")
            print("Session will start when you open Reels.")
        print("Press Ctrl+C to stop\n")

        try:
            if self.manual_session_start:
                self._start_reels_session()
                self._run_manual_session_loop(frame_interval)
            elif use_content:
                self._run_content_detection_loop(frame_interval)
            else:
                self._run_app_detection_loop(frame_interval)
        finally:
            self._shutdown()

    def _run_manual_session_loop(self, frame_interval: float) -> None:
        """Run loop for manual booth sessions started from the UI."""
        while self._running:
            loop_start = time()

            frame = self.capture.capture_screen()
            if frame:
                self._frame_count += 1
                self._capture_failure_count = 0
                if self._session_active:
                    self._process_frame(frame)
            else:
                self._capture_failure_count += 1
                if self._capture_failure_count >= self._max_capture_failures:
                    self._handle_capture_disconnect()
                    break

            elapsed = time() - loop_start
            sleep_time = frame_interval - elapsed
            if sleep_time > 0:
                sleep(sleep_time)

    def _run_app_detection_loop(self, frame_interval: float) -> None:
        """Run the main loop using app-based detection.

        Args:
            frame_interval: Time between frames in seconds.
        """
        while self._running:
            loop_start = time()

            # Check app state
            app_state = self._check_instagram_state()

            # Handle state transitions
            if app_state != self._last_app_state:
                self._handle_state_change(self._last_app_state, app_state)
                self._last_app_state = app_state

            # Only capture frames when in reels mode
            if app_state == AppState.REELS_MODE:
                frame = self.capture.capture_screen()
                if frame:
                    self._frame_count += 1
                    self._capture_failure_count = 0
                    self._process_frame(frame)
                else:
                    self._capture_failure_count += 1
                    if self._capture_failure_count >= self._max_capture_failures:
                        self._handle_capture_disconnect()
                        break

            # Maintain frame rate
            elapsed = time() - loop_start
            sleep_time = frame_interval - elapsed
            if sleep_time > 0:
                sleep(sleep_time)

    def _run_content_detection_loop(self, frame_interval: float) -> None:
        """Run the main loop using content-based detection.

        This mode analyzes screen content to detect when user is viewing Reels,
        useful for mirror mode where app info isn't available.

        Args:
            frame_interval: Time between frames in seconds.
        """
        while self._running:
            loop_start = time()

            # Always capture frames in content detection mode
            frame = self.capture.capture_screen()
            if frame:
                self._frame_count += 1
                self._capture_failure_count = 0

                # Use content detector to determine session state
                content_type, session_started, session_ended = (
                    self.content_detector.process_frame(frame)
                )

                # Handle session state changes
                if session_started and not self._session_active:
                    self._start_reels_session()
                elif session_ended and self._session_active:
                    self._end_reels_session()

                # Process frame for reel detection if in active session
                if self._session_active and content_type == ContentType.REELS:
                    self._process_frame(frame)
            else:
                self._capture_failure_count += 1
                if self._capture_failure_count >= self._max_capture_failures:
                    self._handle_capture_disconnect()
                    break

            # Maintain frame rate
            elapsed = time() - loop_start
            sleep_time = frame_interval - elapsed
            if sleep_time > 0:
                sleep(sleep_time)

    def _start_reels_session(self) -> None:
        """Start a new Reels viewing session."""
        self._session_start = datetime.now()
        self._session_active = True

        # Print session header
        session_start_str = self._session_start.strftime("%Y-%m-%d %H:%M:%S")
        self.printer.print_header(session_start_str)

        # Start time tracking
        self.time_tracker.start_session()

        # Reset detectors for new session
        self.reel_detector.reset()
        # Note: Don't reset content_detector here - it tracks session state

        # Notify callback
        if self.on_session_start:
            self.on_session_start()

        print(f"\n{'=' * 40}")
        print("SESSION STARTED")
        print(f"{'=' * 40}")

    def _handle_capture_disconnect(self) -> None:
        """Handle sustained capture failures, usually mirror disconnect."""
        print("\nMirror feed lost. Ending session.")
        if self._session_active:
            self._end_reels_session()
        self._running = False

    def _end_reels_session(self) -> None:
        """End the current Reels viewing session."""
        if not self._session_active:
            return

        self._session_active = False

        # Stop tracking and get stats
        stats = self.time_tracker.stop_session()

        # Print summary with thank you
        self.printer.print_summary(
            total_reels=stats.total_reels,
            total_time_seconds=stats.total_time,
        )
        self.printer.cut()

        # Get receipt content if available
        receipt_content = ""
        if hasattr(self.printer, "get_receipt_content"):
            receipt_content = self.printer.get_receipt_content()

        # Notify callback
        if self.on_session_end:
            self.on_session_end(stats.total_reels, stats.total_time, receipt_content)

        print(f"\n{'=' * 40}")
        print("SESSION ENDED")
        print(f"Total reels: {stats.total_reels}")
        print(f"Total time: {BasePrinter.format_duration(stats.total_time)}")
        print(f"{'=' * 40}\n")
        print("Waiting for Instagram Reels to start new session...")

    def _handle_state_change(self, old_state: AppState, new_state: AppState) -> None:
        """Handle app state transitions.

        Args:
            old_state: Previous app state.
            new_state: New app state.
        """
        if new_state == AppState.REELS_MODE and not self._session_active:
            # User entered Reels - start session
            self._start_reels_session()
        elif old_state == AppState.REELS_MODE and new_state != AppState.REELS_MODE:
            # User left Reels - end session
            self._end_reels_session()

    def _shutdown(self) -> None:
        """Clean shutdown."""
        # End active session if any
        if self._session_active:
            self._end_reels_session()

        # Close printer
        self.printer.close()

        # Disconnect from device
        self.capture.disconnect()

        # Print final stats
        print(f"\n{'=' * 40}")
        print("TRACKER STOPPED")
        print(f"{'=' * 40}")
        print(f"Frames processed: {self._frame_count}")
        print("Goodbye!")
        print(f"{'=' * 40}\n")

    def stop(self) -> None:
        """Stop the orchestrator."""
        self._running = False
