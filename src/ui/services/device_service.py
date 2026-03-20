"""Background device polling service."""

import asyncio
import time
from typing import Optional

from src.capture.device_detector import DeviceDetector
from src.capture.base import DeviceInfo
from src.capture.mirror_launcher import MirrorLauncher
from src.diagnostics.connection_log import log_connection_event
from src.ui.state import app_state


class DeviceService:
    """Service for polling connected devices."""

    def __init__(self, poll_interval: float = 2.0, auto_launch_mirror: bool = True):
        """Initialize the device service.

        Args:
            poll_interval: Seconds between device polls.
            auto_launch_mirror: Auto-launch ReelTracker uxplay mirror if no device found.
        """
        self.poll_interval = poll_interval
        self.auto_launch_mirror = auto_launch_mirror
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._launch_attempted = False
        self._missing_device_polls = 0
        self._stdout_offset = 0
        self._stderr_offset = 0
        self._last_connected_device_id: Optional[str] = None

    async def start(self) -> None:
        """Start background device polling."""
        if self._running:
            return

        self._running = True
        self._launch_attempted = False
        log_connection_event("device_service_start", f"auto_launch_mirror={self.auto_launch_mirror}")

        # Start uxplay alongside the Python app so no extra terminal is needed.
        if self.auto_launch_mirror:
            loop = asyncio.get_event_loop()
            ok = await loop.run_in_executor(None, self.ensure_pairing_ready, 1.0)
            if not ok:
                log_connection_event("pairing_init_failed", "ensure_pairing_ready returned false")
                raise RuntimeError("Failed to initialize ReelTracker pairing (uxplay).")
            # Mark launch as already handled to avoid immediate PIN rotation
            # on the first polling tick.
            self._launch_attempted = app_state.uxplay_process is not None

        self._task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        """Stop background device polling."""
        self._running = False
        log_connection_event("device_service_stop")
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        self._stop_uxplay()

    async def _poll_loop(self) -> None:
        """Main polling loop."""
        while self._running:
            try:
                await self._poll_devices()
            except Exception:
                pass

            await asyncio.sleep(self.poll_interval)

    async def _poll_devices(self) -> None:
        """Poll for connected devices."""
        self._ingest_uxplay_runtime_logs()

        if not app_state.device_polling:
            return

        # Keep managed uxplay alive if app is expected to manage it.
        if self.auto_launch_mirror:
            process = app_state.uxplay_process
            if process is not None and process.poll() is not None:
                log_connection_event("uxplay_process_exited", f"returncode={process.returncode}")
                app_state.uxplay_process = None
                app_state.uxplay_pairing_code = None
                app_state.notify_update()
                self._launch_attempted = False

        # Run device detection in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        device = await loop.run_in_executor(
            None, DeviceDetector.get_preferred_device
        )

        # If no device found and auto-launch is enabled, try to launch mirroring.
        # Do not relaunch while a device is already considered connected.
        if (
            device is None
            and app_state.connected_device is None
            and self.auto_launch_mirror
            and not self._launch_attempted
            and (
                app_state.uxplay_process is None
                or app_state.uxplay_process.poll() is not None
            )
        ):
            self._launch_attempted = True
            await loop.run_in_executor(None, self._try_auto_launch_mirror)
            # Poll again after launch attempt
            device = await loop.run_in_executor(
                None, DeviceDetector.get_preferred_device
            )

        # Update state if device changed
        current = app_state.connected_device
        if app_state.session_active and current is not None:
            # Lock device while a session is running to enforce one active mirror.
            return
        if device is None and current is not None:
            # Avoid flapping due occasional frame/window detection misses.
            self._missing_device_polls += 1
            if self._missing_device_polls < 3:
                return
            self._missing_device_polls = 0
            # Treat sustained loss as disconnect and immediately rotate pairing
            # so the next participant must enter a fresh PIN.
            app_state.set_device(None)
            log_connection_event("device_disconnected", f"device_id={current.device_id}")
            if self.auto_launch_mirror:
                self.restart_pairing_for_new_session()
            return
        else:
            self._missing_device_polls = 0
        if device != current:
            app_state.set_device(device)
            if device is None:
                if self._last_connected_device_id:
                    log_connection_event("device_disconnected", f"device_id={self._last_connected_device_id}")
                    self._last_connected_device_id = None
            else:
                log_connection_event("device_connected", f"device_id={device.device_id}")
                self._last_connected_device_id = device.device_id

    def _try_auto_launch_mirror(self) -> None:
        """Try to auto-launch a mirroring app."""
        # Booth mode only supports the ReelTracker uxplay mirror.
        if MirrorLauncher.is_uxplay_available():
            log_connection_event("uxplay_auto_launch_attempt")
            # Store the process handle in app_state so we can clean it up
            process, pin = MirrorLauncher.launch_uxplay_with_pin()
            if process:
                app_state.uxplay_process = process
                app_state.uxplay_pairing_code = pin
                app_state.notify_update()
                log_connection_event("pairing_pin_ready", f"pin={pin} pid={process.pid}")
            else:
                log_connection_event("uxplay_auto_launch_failed")
        else:
            log_connection_event("uxplay_not_available_for_auto_launch")

    def ensure_pairing_ready(self, timeout_seconds: float = 3.0) -> bool:
        """Ensure uxplay process and PIN are available within a short deadline."""
        if not self.auto_launch_mirror:
            return True
        log_connection_event("ensure_pairing_ready_start", f"timeout_seconds={timeout_seconds}")

        process = app_state.uxplay_process
        if process is not None and process.poll() is not None:
            app_state.uxplay_process = None
            app_state.uxplay_pairing_code = None
            app_state.notify_update()

        # Fast path: already alive and PIN present.
        process = app_state.uxplay_process
        if process is not None and process.poll() is None and app_state.uxplay_pairing_code:
            log_connection_event(
                "ensure_pairing_ready_fast_path",
                f"pid={process.pid} pin={app_state.uxplay_pairing_code}",
            )
            return True

        self._try_auto_launch_mirror()

        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            process = app_state.uxplay_process
            if process is not None and process.poll() is None and app_state.uxplay_pairing_code:
                log_connection_event(
                    "ensure_pairing_ready_success",
                    f"pid={process.pid} pin={app_state.uxplay_pairing_code}",
                )
                return True
            # Tiny sleep keeps startup responsive while allowing process state to settle.
            time.sleep(0.05)
        log_connection_event("ensure_pairing_ready_timeout")
        return False

    def _stop_uxplay(self) -> None:
        """Terminate managed uxplay process."""
        process = app_state.uxplay_process
        if process is None:
            return
        log_connection_event("uxplay_stop_requested", f"pid={process.pid}")
        try:
            process.terminate()
            try:
                process.wait(timeout=3.0)
            except Exception:
                process.kill()
                log_connection_event("uxplay_force_kill", f"pid={process.pid}")
        except Exception:
            pass
        finally:
            app_state.uxplay_process = None
            app_state.uxplay_pairing_code = None
            app_state.notify_update()
            log_connection_event("uxplay_stopped")

    def restart_pairing_for_new_session(self) -> bool:
        """Restart uxplay so each session has a fresh pairing PIN."""
        log_connection_event("pairing_rotation_requested")
        self._stop_uxplay()
        self._launch_attempted = False
        self._try_auto_launch_mirror()
        if app_state.uxplay_pairing_code:
            log_connection_event("pairing_rotated", f"pin={app_state.uxplay_pairing_code}")
        return app_state.uxplay_process is not None

    def stop_pairing_after_session(self) -> None:
        """Stop uxplay after session completion to end pairing window."""
        log_connection_event("stop_pairing_after_session")
        self._stop_uxplay()

    def prime_next_user_pairing(self) -> bool:
        """Immediately rotate pairing so the next user can connect with minimal delay."""
        log_connection_event("prime_next_user_pairing")
        return self.restart_pairing_for_new_session()

    @staticmethod
    def _classify_uxplay_line(line: str, stream: str) -> Optional[tuple[str, str]]:
        """Map raw uxplay output lines to diagnostics events."""
        text = line.strip()
        if not text:
            return None
        lower = text.lower()

        if "initialized server socket" in lower:
            return "uxplay_advertising_ready", text
        if "begin streaming to gstreamer video pipeline" in lower:
            return "uxplay_stream_started", text
        if "connection closed on socket" in lower or "removing connection for socket" in lower:
            return "uxplay_client_disconnected", text
        if "raop_rtp_mirror->running is no longer true" in lower or "stopping raop server" in lower:
            return "uxplay_stream_stopped", text
        if "rtsp" in lower and "connection" in lower:
            return "uxplay_rtsp_connection", text
        if "pin" in lower and ("pair" in lower or "auth" in lower or "prompt" in lower):
            return "uxplay_pin_event", text
        if "failed" in lower or "critical" in lower or "error" in lower:
            return f"uxplay_{stream}_warning", text
        return None

    def _read_new_lines(self, path: str, offset: int) -> tuple[list[str], int]:
        """Read new lines from a log file based on byte offset."""
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                handle.seek(0, 2)
                size = handle.tell()
                if offset > size:
                    offset = 0
                handle.seek(offset)
                data = handle.read()
                new_offset = handle.tell()
        except Exception:
            return [], offset

        if not data:
            return [], new_offset
        return data.splitlines(), new_offset

    def _ingest_uxplay_runtime_logs(self) -> None:
        """Ingest new uxplay stdout/stderr lines and emit structured diagnostics events."""
        stdout_lines, self._stdout_offset = self._read_new_lines("output/uxplay.stdout.log", self._stdout_offset)
        stderr_lines, self._stderr_offset = self._read_new_lines("output/uxplay.stderr.log", self._stderr_offset)

        for line in stdout_lines:
            event = self._classify_uxplay_line(line, "stdout")
            if event is not None:
                log_connection_event(event[0], event[1])

        for line in stderr_lines:
            event = self._classify_uxplay_line(line, "stderr")
            if event is not None:
                log_connection_event(event[0], event[1])

    def get_all_devices(self) -> list[DeviceInfo]:
        """Get all currently connected devices (synchronous)."""
        return DeviceDetector.detect_all_devices()


# Singleton instance
device_service = DeviceService()
