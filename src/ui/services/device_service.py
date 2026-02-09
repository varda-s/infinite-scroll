"""Background device polling service."""

import asyncio
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
            auto_launch_mirror: Auto-launch iPhone Mirroring if no device found.
        """
        self.poll_interval = poll_interval
        self.auto_launch_mirror = auto_launch_mirror
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._launch_attempted = False

    async def start(self) -> None:
        """Start background device polling."""
        if self._running:
            return

        self._running = True
        self._launch_attempted = False
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

        # Run device detection in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        device = await loop.run_in_executor(
            None, DeviceDetector.get_preferred_device
        )

        # If no device found and auto-launch is enabled, try to launch mirroring
        if device is None and self.auto_launch_mirror and not self._launch_attempted:
            self._launch_attempted = True
            await loop.run_in_executor(None, self._try_auto_launch_mirror)
            # Poll again after launch attempt
            device = await loop.run_in_executor(
                None, DeviceDetector.get_preferred_device
            )

        # Update state if device changed
        current = app_state.connected_device
        if device != current:
            app_state.set_device(device)

    def _try_auto_launch_mirror(self) -> None:
        """Try to auto-launch a mirroring app."""
        # Try iPhone Mirroring first (best experience)
        if MirrorLauncher.is_iphone_mirroring_available():
            if MirrorLauncher.ensure_mirroring_running():
                return

        # Fall back to uxplay if available
        if MirrorLauncher.is_uxplay_available():
            # Store the process handle in app_state so we can clean it up
            process = MirrorLauncher.launch_uxplay()
            if process:
                app_state.uxplay_process = process

    def get_all_devices(self) -> list[DeviceInfo]:
        """Get all currently connected devices (synchronous)."""
        return DeviceDetector.detect_all_devices()


# Singleton instance
device_service = DeviceService()
