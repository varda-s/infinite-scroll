"""Background device polling service."""

import asyncio
import time
from typing import Optional

from src.capture.device_detector import DeviceDetector
from src.capture.base import DeviceInfo
from src.capture.mirror_launcher import MirrorLauncher
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

    async def start(self) -> None:
        """Start background device polling."""
        if self._running:
            return

        self._running = True
        self._launch_attempted = False

        # Start uxplay alongside the Python app so no extra terminal is needed.
        if self.auto_launch_mirror:
            loop = asyncio.get_event_loop()
            ok = await loop.run_in_executor(None, self.ensure_pairing_ready, 1.0)
            if not ok:
                raise RuntimeError("Failed to initialize ReelTracker pairing (uxplay).")
            # Mark launch as already handled to avoid immediate PIN rotation
            # on the first polling tick.
            self._launch_attempted = app_state.uxplay_process is not None

        self._task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        """Stop background device polling."""
        self._running = False
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
        if not app_state.device_polling:
            return

        # Keep managed uxplay alive if app is expected to manage it.
        if self.auto_launch_mirror:
            process = app_state.uxplay_process
            if process is not None and process.poll() is not None:
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
            if self.auto_launch_mirror:
                self.restart_pairing_for_new_session()
            return
        else:
            self._missing_device_polls = 0
        if device != current:
            app_state.set_device(device)

    def _try_auto_launch_mirror(self) -> None:
        """Try to auto-launch a mirroring app."""
        # Booth mode only supports the ReelTracker uxplay mirror.
        if MirrorLauncher.is_uxplay_available():
            # Store the process handle in app_state so we can clean it up
            process, pin = MirrorLauncher.launch_uxplay_with_pin()
            if process:
                app_state.uxplay_process = process
                app_state.uxplay_pairing_code = pin
                app_state.notify_update()

    def ensure_pairing_ready(self, timeout_seconds: float = 3.0) -> bool:
        """Ensure uxplay process and PIN are available within a short deadline."""
        if not self.auto_launch_mirror:
            return True

        process = app_state.uxplay_process
        if process is not None and process.poll() is not None:
            app_state.uxplay_process = None
            app_state.uxplay_pairing_code = None
            app_state.notify_update()

        # Fast path: already alive and PIN present.
        process = app_state.uxplay_process
        if process is not None and process.poll() is None and app_state.uxplay_pairing_code:
            return True

        self._try_auto_launch_mirror()

        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            process = app_state.uxplay_process
            if process is not None and process.poll() is None and app_state.uxplay_pairing_code:
                return True
            # Tiny sleep keeps startup responsive while allowing process state to settle.
            time.sleep(0.05)
        return False

    def _stop_uxplay(self) -> None:
        """Terminate managed uxplay process."""
        process = app_state.uxplay_process
        if process is None:
            return
        try:
            process.terminate()
            try:
                process.wait(timeout=3.0)
            except Exception:
                process.kill()
        except Exception:
            pass
        finally:
            app_state.uxplay_process = None
            app_state.uxplay_pairing_code = None
            app_state.notify_update()

    def restart_pairing_for_new_session(self) -> bool:
        """Restart uxplay so each session has a fresh pairing PIN."""
        self._stop_uxplay()
        self._launch_attempted = False
        self._try_auto_launch_mirror()
        return app_state.uxplay_process is not None

    def stop_pairing_after_session(self) -> None:
        """Stop uxplay after session completion to end pairing window."""
        self._stop_uxplay()

    def prime_next_user_pairing(self) -> bool:
        """Immediately rotate pairing so the next user can connect with minimal delay."""
        return self.restart_pairing_for_new_session()

    def get_all_devices(self) -> list[DeviceInfo]:
        """Get all currently connected devices (synchronous)."""
        return DeviceDetector.detect_all_devices()


# Singleton instance
device_service = DeviceService()
