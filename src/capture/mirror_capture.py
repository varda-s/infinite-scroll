"""iPhone-to-Mac Mirroring Connector.

This connector captures the iPhone screen via QuickTime or other macOS mirroring apps.
No developer mode or special setup required on the iPhone - just USB connection and trust.

This is the recommended connector for iPhone users on macOS.
"""

import subprocess
import re
from dataclasses import dataclass
from typing import Optional

from PIL import Image

try:
    import Quartz
    HAS_QUARTZ = True
except ImportError:
    HAS_QUARTZ = False

from src.capture.base import BaseCapture, DeviceInfo, DeviceType, ForegroundApp


@dataclass
class MirrorSource:
    """Information about a detected mirror source."""

    window_id: int
    window_name: str
    app_name: str
    bounds: tuple[int, int, int, int]  # x, y, width, height


class MirrorDetector:
    """Detect iPhone mirroring windows on macOS."""

    # Known iOS mirror apps on macOS (priority order)
    MIRROR_APPS = [
        "iPhone Mirroring",  # macOS Sequoia (15+) native wireless mirroring
        "QuickTime Player",  # Built-in macOS app, USB mirroring (fallback)
        "AirPlay",
        "Screen Mirroring",
        "Reflector",
        "LonelyScreen",
        "AirServer",
        "5KPlayer",
        "X-Mirage",
        "Bezel",  # iPhone mockup app with mirroring
        "uxplay",  # Open-source AirPlay receiver
        "UxPlay",
        "GStreamer",  # uxplay uses GStreamer for video output
    ]

    # Keywords in window titles that indicate an iPhone mirror
    PHONE_KEYWORDS = [
        "iphone", "ipad", "ipod", "ios",
        "screen mirror", "mirroring", "recording",
    ]

    @classmethod
    def detect_mirror_windows(cls) -> list[MirrorSource]:
        """Detect windows that appear to be iPhone mirrors.

        Returns:
            List of detected mirror sources.
        """
        # Try Quartz-based detection first (more reliable for GStreamer/uxplay)
        if HAS_QUARTZ:
            mirrors = cls._detect_with_quartz()
            if mirrors:
                return mirrors

        mirrors = []

        # Check iPhone Mirroring first (macOS Sequoia native wireless mirroring)
        try:
            script = '''
            tell application "System Events"
                if exists process "iPhone Mirroring" then
                    tell process "iPhone Mirroring"
                        set windowCount to count of windows
                        if windowCount > 0 then
                            set win to window 1
                            set winName to name of win
                            set winPos to position of win
                            set winSize to size of win
                            return winName & "|" & (item 1 of winPos) & "|" & (item 2 of winPos) & "|" & (item 1 of winSize) & "|" & (item 2 of winSize)
                        end if
                    end tell
                end if
                return ""
            end tell
            '''
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                parts = result.stdout.strip().split("|")
                if len(parts) >= 5:
                    mirrors.append(MirrorSource(
                        window_id=0,
                        window_name=parts[0] or "iPhone",
                        app_name="iPhone Mirroring",
                        bounds=(
                            int(parts[1]),
                            int(parts[2]),
                            int(parts[3]),
                            int(parts[4]),
                        ),
                    ))
        except Exception as e:
            print(f"iPhone Mirroring detection error: {e}")

        if mirrors:
            return mirrors

        # Check QuickTime Player (USB mirroring fallback)
        try:
            script = '''
            tell application "System Events"
                if exists process "QuickTime Player" then
                    tell process "QuickTime Player"
                        set windowCount to count of windows
                        if windowCount > 0 then
                            set win to window 1
                            set winName to name of win
                            set winPos to position of win
                            set winSize to size of win
                            return winName & "|" & (item 1 of winPos) & "|" & (item 2 of winPos) & "|" & (item 1 of winSize) & "|" & (item 2 of winSize)
                        end if
                    end tell
                end if
                return ""
            end tell
            '''
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                parts = result.stdout.strip().split("|")
                if len(parts) >= 5:
                    mirrors.append(MirrorSource(
                        window_id=0,
                        window_name=parts[0] or "iPhone",
                        app_name="QuickTime Player",
                        bounds=(
                            int(parts[1]),
                            int(parts[2]),
                            int(parts[3]),
                            int(parts[4]),
                        ),
                    ))
        except Exception as e:
            print(f"QuickTime detection error: {e}")

        if mirrors:
            return mirrors

        # Check for uxplay/GStreamer windows specifically
        # uxplay uses GStreamer which may have various process names
        uxplay_mirrors = cls._detect_uxplay_windows()
        if uxplay_mirrors:
            return uxplay_mirrors

        # Check other known mirror apps
        for app_name in cls.MIRROR_APPS:
            if app_name in ("iPhone Mirroring", "QuickTime Player"):
                continue  # Already checked
            try:
                script = f'''
                tell application "System Events"
                    if exists process "{app_name}" then
                        tell process "{app_name}"
                            if (count of windows) > 0 then
                                set win to window 1
                                set winName to name of win
                                set winPos to position of win
                                set winSize to size of win
                                return winName & "|" & (item 1 of winPos) & "|" & (item 2 of winPos) & "|" & (item 1 of winSize) & "|" & (item 2 of winSize)
                            end if
                        end tell
                    end if
                    return ""
                end tell
                '''
                result = subprocess.run(
                    ["osascript", "-e", script],
                    capture_output=True,
                    text=True,
                    timeout=3,
                )
                if result.returncode == 0 and result.stdout.strip():
                    parts = result.stdout.strip().split("|")
                    if len(parts) >= 5:
                        mirrors.append(MirrorSource(
                            window_id=0,
                            window_name=parts[0] or app_name,
                            app_name=app_name,
                            bounds=(
                                int(parts[1]),
                                int(parts[2]),
                                int(parts[3]),
                                int(parts[4]),
                            ),
                        ))
                        break  # Found a mirror, stop looking
            except Exception:
                pass

        return mirrors

    @classmethod
    def _detect_with_quartz(cls) -> list[MirrorSource]:
        """Detect mirror windows using Quartz CGWindowListCopyWindowInfo.

        This method is more reliable for detecting GStreamer/uxplay windows
        that don't register with AppleScript.

        Returns:
            List of detected mirror sources.
        """
        if not HAS_QUARTZ:
            return []

        mirrors = []

        try:
            # Get all on-screen windows
            windows = Quartz.CGWindowListCopyWindowInfo(
                Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements,
                Quartz.kCGNullWindowID
            )

            for win in windows:
                owner = win.get('kCGWindowOwnerName', '')
                name = win.get('kCGWindowName', '')
                layer = win.get('kCGWindowLayer', 0)
                bounds = win.get('kCGWindowBounds', {})
                width = int(bounds.get('Width', 0))
                height = int(bounds.get('Height', 0))
                x = int(bounds.get('X', 0))
                y = int(bounds.get('Y', 0))
                window_id = win.get('kCGWindowNumber', 0)

                # Skip non-normal windows (layer 0 = normal window)
                if layer != 0:
                    continue

                # Skip tiny windows
                if width < 200 or height < 200:
                    continue

                # Check if this is a known mirror app
                owner_lower = owner.lower()
                is_mirror = False
                app_name = owner

                # Check known mirror apps
                for mirror_app in cls.MIRROR_APPS:
                    if mirror_app.lower() in owner_lower:
                        is_mirror = True
                        app_name = mirror_app
                        break

                # Also check for portrait aspect ratio (phone screen)
                # Typical phone is ~9:16 ratio, so height > width * 1.5
                is_portrait = height > width * 1.3

                # uxplay and gstreamer windows with portrait ratio are mirrors
                if owner_lower in ('uxplay', 'gst-play-1.0', 'gstreamer') and is_portrait:
                    is_mirror = True
                    app_name = "uxplay"

                if is_mirror:
                    mirrors.append(MirrorSource(
                        window_id=window_id,
                        window_name=name or f"{owner} Mirror",
                        app_name=app_name,
                        bounds=(x, y, width, height),
                    ))

        except Exception as e:
            print(f"Quartz detection error: {e}")

        return mirrors

    @classmethod
    def _detect_uxplay_windows(cls) -> list[MirrorSource]:
        """Detect uxplay/GStreamer windows.

        uxplay uses GStreamer for video output, which may have various
        process names like gst-play-1.0, gst-launch-1.0, etc.

        Returns:
            List of detected uxplay mirror sources.
        """
        mirrors = []

        # GStreamer process names that uxplay might use
        gst_processes = ["gst-play-1.0", "gst-launch-1.0", "gst_play", "GStreamer"]

        for proc_name in gst_processes:
            try:
                script = f'''
                tell application "System Events"
                    set foundWindows to ""
                    repeat with proc in (every process whose name contains "{proc_name}")
                        try
                            if (count of windows of proc) > 0 then
                                set win to window 1 of proc
                                set winName to name of win
                                set winPos to position of win
                                set winSize to size of win
                                return winName & "|" & (item 1 of winPos) & "|" & (item 2 of winPos) & "|" & (item 1 of winSize) & "|" & (item 2 of winSize)
                            end if
                        end try
                    end repeat
                    return ""
                end tell
                '''
                result = subprocess.run(
                    ["osascript", "-e", script],
                    capture_output=True,
                    text=True,
                    timeout=3,
                )
                if result.returncode == 0 and result.stdout.strip():
                    parts = result.stdout.strip().split("|")
                    if len(parts) >= 5:
                        mirrors.append(MirrorSource(
                            window_id=0,
                            window_name=parts[0] or "uxplay",
                            app_name="uxplay",
                            bounds=(
                                int(parts[1]),
                                int(parts[2]),
                                int(parts[3]),
                                int(parts[4]),
                            ),
                        ))
                        return mirrors
            except Exception:
                pass

        return mirrors

    @staticmethod
    def _parse_applescript_list(output: str) -> list[list[str]]:
        """Parse AppleScript list output into Python lists."""
        # AppleScript returns nested lists like: {{app, win, x, y, w, h}, ...}
        result = []

        # Remove outer braces and split by }, {
        output = output.strip()
        if output.startswith("{") and output.endswith("}"):
            output = output[1:-1]

        # Split into individual window entries
        entries = re.split(r'\},\s*\{', output)

        for entry in entries:
            entry = entry.strip().strip("{}")
            # Split by comma, handling quoted strings
            parts = []
            current = ""
            in_quotes = False
            for char in entry:
                if char == '"':
                    in_quotes = not in_quotes
                elif char == ',' and not in_quotes:
                    parts.append(current.strip().strip('"'))
                    current = ""
                    continue
                current += char
            if current:
                parts.append(current.strip().strip('"'))
            if parts:
                result.append(parts)

        return result

    @classmethod
    def debug_all_windows(cls) -> list[dict]:
        """Get all visible windows for debugging.

        Returns:
            List of dicts with app_name, window_name, and is_mirror_candidate.
        """
        windows_info = []

        try:
            script = '''
            tell application "System Events"
                set output to ""
                repeat with proc in (every process whose background only is false)
                    set procName to name of proc
                    try
                        repeat with win in (every window of proc)
                            set winName to name of win
                            set output to output & procName & "|" & winName & "\\n"
                        end repeat
                    end try
                end repeat
                return output
            end tell
            '''

            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode == 0 and result.stdout.strip():
                for line in result.stdout.strip().split("\n"):
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split("|")
                    if len(parts) >= 2:
                        app_name = parts[0]
                        window_name = parts[1]

                        # Check if this would be detected as an iPhone mirror
                        is_mirror = app_name in cls.MIRROR_APPS
                        if not is_mirror and window_name:
                            window_lower = window_name.lower()
                            if any(kw in window_lower for kw in cls.PHONE_KEYWORDS):
                                is_mirror = True

                        windows_info.append({
                            "app_name": app_name,
                            "window_name": window_name,
                            "is_mirror_candidate": is_mirror,
                        })

        except Exception as e:
            windows_info.append({"error": str(e)})

        return windows_info


class MirrorCapture(BaseCapture):
    """Capture screenshots from a screen mirroring window."""

    def __init__(self, mirror_source: Optional[MirrorSource] = None):
        """Initialize mirror capture.

        Args:
            mirror_source: Specific mirror source to use, or None to auto-detect.
        """
        self._mirror_source = mirror_source
        self._device_info: Optional[DeviceInfo] = None
        self._connected = False

    @property
    def device_info(self) -> DeviceInfo:
        """Get device information."""
        if self._device_info is None:
            raise RuntimeError("Not connected to mirror source")
        return self._device_info

    @property
    def is_connected(self) -> bool:
        """Check if connected to mirror source."""
        return self._connected

    def connect(self) -> bool:
        """Connect to a mirror source."""
        if self._mirror_source is None:
            # Auto-detect
            mirrors = MirrorDetector.detect_mirror_windows()
            if not mirrors:
                return False
            self._mirror_source = mirrors[0]

        self._device_info = DeviceInfo(
            device_type=DeviceType.IOS,
            device_id=f"mirror:{self._mirror_source.app_name}",
            device_name=f"{self._mirror_source.window_name} (Mirror)",
            model=self._mirror_source.app_name,
            connection_type="mirror",
        )

        self._connected = True
        return True

    def disconnect(self) -> None:
        """Disconnect from mirror source."""
        self._connected = False
        self._mirror_source = None
        self._device_info = None

    def capture_screen(self) -> Optional[Image.Image]:
        """Capture screenshot from the mirror window."""
        if not self._connected or self._mirror_source is None:
            return None

        try:
            import tempfile
            import os

            # Create temp file for screenshot
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                temp_path = f.name

            # Try window ID capture first (more reliable for uxplay/GStreamer)
            window_id = self._mirror_source.window_id
            if window_id and window_id > 0:
                result = subprocess.run(
                    ["screencapture", "-l", str(window_id), "-x", temp_path],
                    capture_output=True,
                    timeout=5,
                )
            else:
                # Fall back to region capture
                x, y, w, h = self._mirror_source.bounds
                result = subprocess.run(
                    ["screencapture", "-R", f"{x},{y},{w},{h}", "-x", temp_path],
                    capture_output=True,
                    timeout=5,
                )

            if result.returncode != 0:
                os.unlink(temp_path) if os.path.exists(temp_path) else None
                return None

            # Load and return the image
            image = Image.open(temp_path)
            image.load()  # Force load before deleting file

            # Clean up
            os.unlink(temp_path)

            return image

        except Exception:
            return None

    def get_foreground_app(self) -> Optional[ForegroundApp]:
        """Get foreground app info - always returns Instagram for mirror mode.

        In mirror mode, we assume the user is showing Instagram Reels.
        The reel detection will handle the actual content analysis.
        """
        # For mirror mode, we can't detect the foreground app
        # We'll assume Instagram Reels and let the detector handle it
        return ForegroundApp(
            package_name="com.instagram.android",
            activity="reels",  # Assume reels mode
        )


def get_available_mirrors() -> list[MirrorSource]:
    """Get list of available mirror sources.

    Returns:
        List of detected mirror sources.
    """
    return MirrorDetector.detect_mirror_windows()
