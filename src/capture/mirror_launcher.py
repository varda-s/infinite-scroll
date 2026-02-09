"""Auto-launch iPhone mirroring apps for touchless experience."""

import subprocess
import time
from pathlib import Path
from typing import Optional


class MirrorLauncher:
    """Launch and manage iPhone mirroring applications."""

    # Paths to known mirroring apps
    IPHONE_MIRRORING_APP = "/System/Applications/iPhone Mirroring.app"
    QUICKTIME_APP = "/System/Applications/QuickTime Player.app"

    @classmethod
    def is_iphone_mirroring_available(cls) -> bool:
        """Check if iPhone Mirroring app is available (macOS 15+)."""
        return Path(cls.IPHONE_MIRRORING_APP).exists()

    @classmethod
    def is_iphone_mirroring_running(cls) -> bool:
        """Check if iPhone Mirroring app is already running."""
        try:
            result = subprocess.run(
                ["pgrep", "-x", "iPhone Mirroring"],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except Exception:
            return False

    @classmethod
    def launch_iphone_mirroring(cls, wait_for_window: bool = True) -> bool:
        """Launch iPhone Mirroring app.

        Args:
            wait_for_window: Wait for the mirroring window to appear.

        Returns:
            True if successfully launched.
        """
        if not cls.is_iphone_mirroring_available():
            return False

        try:
            # Launch the app
            subprocess.run(
                ["open", "-a", "iPhone Mirroring"],
                capture_output=True,
                timeout=10,
            )

            if wait_for_window:
                # Wait for the window to appear (up to 10 seconds)
                for _ in range(20):
                    time.sleep(0.5)
                    if cls._has_mirroring_window():
                        return True

            return cls.is_iphone_mirroring_running()

        except Exception:
            return False

    @classmethod
    def _has_mirroring_window(cls) -> bool:
        """Check if iPhone Mirroring has an open window."""
        try:
            script = '''
            tell application "System Events"
                if exists process "iPhone Mirroring" then
                    tell process "iPhone Mirroring"
                        return (count of windows) > 0
                    end tell
                end if
                return false
            end tell
            '''
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0 and "true" in result.stdout.lower()
        except Exception:
            return False

    @classmethod
    def position_mirroring_window(
        cls,
        x: int = 50,
        y: int = 50,
        width: Optional[int] = None,
        height: Optional[int] = None,
    ) -> bool:
        """Position the iPhone Mirroring window.

        Args:
            x: X position from left.
            y: Y position from top.
            width: Optional width (keeps current if None).
            height: Optional height (keeps current if None).

        Returns:
            True if successfully positioned.
        """
        try:
            size_cmd = ""
            if width and height:
                size_cmd = f"set size of win to {{{width}, {height}}}"

            script = f'''
            tell application "System Events"
                if exists process "iPhone Mirroring" then
                    tell process "iPhone Mirroring"
                        if (count of windows) > 0 then
                            set win to window 1
                            set position of win to {{{x}, {y}}}
                            {size_cmd}
                            return true
                        end if
                    end tell
                end if
                return false
            end tell
            '''
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0 and "true" in result.stdout.lower()
        except Exception:
            return False

    @classmethod
    def ensure_mirroring_running(
        cls,
        position_x: int = 50,
        position_y: int = 100,
    ) -> bool:
        """Ensure iPhone Mirroring is running and positioned.

        This is the main entry point for touchless setup.

        Args:
            position_x: X position for the window.
            position_y: Y position for the window.

        Returns:
            True if mirroring is ready.
        """
        # Check if already running with a window
        if cls.is_iphone_mirroring_running() and cls._has_mirroring_window():
            # Just position it
            cls.position_mirroring_window(x=position_x, y=position_y)
            return True

        # Try to launch
        if cls.launch_iphone_mirroring(wait_for_window=True):
            # Position the window
            cls.position_mirroring_window(x=position_x, y=position_y)
            return True

        return False

    @classmethod
    def is_uxplay_available(cls) -> bool:
        """Check if uxplay is installed."""
        try:
            result = subprocess.run(
                ["which", "uxplay"],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except Exception:
            return False

    @classmethod
    def launch_uxplay(cls) -> Optional[subprocess.Popen]:
        """Launch uxplay as a subprocess.

        Returns:
            The subprocess handle, or None if failed.
        """
        if not cls.is_uxplay_available():
            return None

        try:
            # Launch uxplay in the background
            # uxplay creates its own window for the AirPlay stream
            process = subprocess.Popen(
                ["uxplay", "-n", "ReelTracker"],  # -n sets the AirPlay name
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            return process
        except Exception:
            return None
