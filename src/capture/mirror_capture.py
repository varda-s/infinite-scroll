"""iPhone-to-Mac Mirroring Connector.

This connector captures the iPhone screen via QuickTime or other macOS mirroring apps.
No developer mode or special setup required on the iPhone - just USB connection and trust.

This is the recommended connector for iPhone users on macOS.
"""

import os
import subprocess
import re
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

from PIL import Image, ImageStat

try:
    import Quartz
    HAS_QUARTZ = True
except ImportError:
    HAS_QUARTZ = False

from src.capture.base import BaseCapture, DeviceInfo, DeviceType, ForegroundApp
from src.detection.image_utils import compute_phash


@dataclass
class MirrorSource:
    """Information about a detected mirror source."""

    window_id: int
    window_name: str
    app_name: str
    bounds: tuple[int, int, int, int]  # x, y, width, height


class MirrorDetector:
    """Detect iPhone mirroring windows on macOS."""

    # ReelTracker booth mode only supports uxplay/GStreamer-backed mirrors.
    REELDETECTOR_APP_KEYWORDS = ("uxplay", "gstreamer", "gst-play", "gst-launch", "gst_play")
    REELDETECTOR_WINDOW_KEYWORDS = ("reeltracker",)

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
    def is_reeldetector_source(cls, source: MirrorSource) -> bool:
        """Return True if this mirror source matches the ReelTracker mirror pipeline."""
        app_name = source.app_name.lower()
        window_name = source.window_name.lower()

        if not any(keyword in app_name for keyword in cls.REELDETECTOR_APP_KEYWORDS):
            return False

        # Prefer explicitly named uxplay window if present.
        if any(keyword in window_name for keyword in cls.REELDETECTOR_WINDOW_KEYWORDS):
            return True

        # UxPlay commonly presents as "OpenGL renderer". Treat that as valid even
        # when the window title does not include ReelTracker.
        if "opengl renderer" in window_name:
            return True

        # Fallback for uxplay/gstreamer windows where title may not include
        # ReelTracker. Accept any reasonably sized render window; aspect ratio is
        # not reliable across renderers/displays.
        _, _, width, height = source.bounds
        return width >= 200 and height >= 200

    @classmethod
    def detect_reeldetector_windows(cls) -> list[MirrorSource]:
        """Detect only mirror windows supported by ReelTracker booth mode."""
        mirrors = cls.detect_mirror_windows()
        return [source for source in mirrors if cls.is_reeldetector_source(source)]

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
            # Include all windows so mirror detection works across Spaces and
            # when the mirror window is not the currently focused/main window.
            windows = Quartz.CGWindowListCopyWindowInfo(
                Quartz.kCGWindowListOptionAll,
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

                # Skip non-normal window layers for unknown apps, but allow
                # known mirror processes to pass even if they are not focused.
                if layer != 0 and not is_mirror:
                    continue

                # Skip tiny windows (except known mirror app owners)
                if width < 120 or height < 120:
                    continue

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

        # Prefer larger windows first to reduce accidental tiny-window matches
        mirrors.sort(key=lambda m: m.bounds[2] * m.bounds[3], reverse=True)
        return mirrors

    @staticmethod
    def _capture_window_image(window_id: int) -> Optional[Image.Image]:
        """Capture a specific window via Quartz."""
        if not HAS_QUARTZ or window_id <= 0:
            return None

        try:
            image_ref = Quartz.CGWindowListCreateImage(
                Quartz.CGRectNull,
                Quartz.kCGWindowListOptionIncludingWindow,
                window_id,
                Quartz.kCGWindowImageBoundsIgnoreFraming | Quartz.kCGWindowImageNominalResolution,
            )
            if image_ref is None:
                return None

            width = Quartz.CGImageGetWidth(image_ref)
            height = Quartz.CGImageGetHeight(image_ref)
            if width < 120 or height < 120:
                return None

            bytes_per_row = Quartz.CGImageGetBytesPerRow(image_ref)
            provider = Quartz.CGImageGetDataProvider(image_ref)
            data = Quartz.CGDataProviderCopyData(provider)
            image = Image.frombuffer(
                "RGBA",
                (width, height),
                bytes(data),
                "raw",
                "BGRA",
                bytes_per_row,
                1,
            )
            return image.convert("RGB")
        except Exception:
            return None

    @classmethod
    def is_stream_active(cls, source: MirrorSource) -> bool:
        """Best-effort check that the mirror source currently shows active video."""
        # If we can't verify via window id, keep source usable.
        if source.window_id <= 0:
            return True

        # Stream-state validation is mainly needed for uxplay/GStreamer windows.
        app_name = source.app_name.lower()
        if "uxplay" not in app_name and "gstreamer" not in app_name and "gst" not in app_name:
            return True

        image = cls._capture_window_image(source.window_id)
        if image is None:
            # If we can't sample pixels, fall back to uxplay runtime log state.
            # This avoids false "connected" signals when no phone is paired.
            return cls._uxplay_log_stream_active()

        gray = image.convert("L")
        hist = gray.histogram()
        total = float(sum(hist))
        if total <= 0:
            return False

        non_dark_ratio = (total - float(sum(hist[:18]))) / total
        contrast = ImageStat.Stat(gray).stddev[0]

        # Inactive uxplay windows are usually nearly black with very low variance.
        return non_dark_ratio > 0.04 and contrast > 4.0

    @staticmethod
    def _uxplay_log_stream_active() -> bool:
        """Infer active stream state from recent uxplay stdout log lines."""
        log_path = Path("output/uxplay.stdout.log")
        if not log_path.exists():
            return False
        try:
            lines = log_path.read_text(errors="ignore").splitlines()
        except Exception:
            return False
        if not lines:
            return False

        tail = lines[-600:]
        last_stream = -1
        last_end = -1
        for idx, line in enumerate(tail):
            text = line.strip()
            if "Begin streaming to GStreamer video pipeline" in text:
                last_stream = idx
            if (
                "Connection closed on socket" in text
                or "Removing connection for socket" in text
                or "raop_rtp_mirror->running is no longer true" in text
                or "Stopping RAOP Server" in text
            ):
                last_end = idx
        return last_stream >= 0 and last_stream > last_end

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
        self._static_frame_streak = 0
        self._prev_small_hash: Optional[str] = None

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
            # Auto-detect only ReelTracker-compatible mirrors.
            mirrors = MirrorDetector.detect_reeldetector_windows()
            if not mirrors:
                return False
            self._mirror_source = mirrors[0]
        elif self._mirror_source.window_id <= 0:
            self._resolve_window_id()

        self._device_info = DeviceInfo(
            device_type=DeviceType.IOS,
            device_id=f"mirror:{self._mirror_source.app_name}",
            device_name=f"{self._mirror_source.window_name} (Mirror)",
            model=self._mirror_source.app_name,
            connection_type="mirror",
        )

        self._connected = True
        self._static_frame_streak = 0
        self._prev_small_hash = None
        return True

    def disconnect(self) -> None:
        """Disconnect from mirror source."""
        self._connected = False
        self._mirror_source = None
        self._device_info = None
        self._static_frame_streak = 0
        self._prev_small_hash = None

    def _capture_with_quartz(self) -> Optional[Image.Image]:
        """Capture mirror window with Quartz APIs (faster than screencapture)."""
        if self._mirror_source is None:
            return None
        return MirrorDetector._capture_window_image(self._mirror_source.window_id)

    def _resolve_window_id(self) -> None:
        """Resolve missing/invalid window ids via Quartz for background-safe capture."""
        if self._mirror_source is None or not HAS_QUARTZ:
            return
        if self._mirror_source.window_id > 0:
            return

        candidates = MirrorDetector.detect_reeldetector_windows()
        if not candidates:
            return

        current_name = self._mirror_source.window_name.lower()
        current_app = self._mirror_source.app_name.lower()

        best: Optional[MirrorSource] = None
        for source in candidates:
            app_match = source.app_name.lower() == current_app or current_app in source.app_name.lower()
            name_match = current_name in source.window_name.lower() or source.window_name.lower() in current_name
            if app_match and name_match:
                best = source
                break

        if best is None:
            # Fall back to first ReelTracker mirror source.
            best = candidates[0]

        self._mirror_source = best

    def capture_screen(self) -> Optional[Image.Image]:
        """Capture screenshot from the mirror window."""
        if not self._connected or self._mirror_source is None:
            return None

        # Guard against stale sessions: if the AirPlay stream is gone, fail fast
        # so orchestrator can stop the session instead of processing frozen frames.
        if not MirrorDetector.is_stream_active(self._mirror_source):
            return None

        try:
            if self._mirror_source.window_id <= 0:
                self._resolve_window_id()

            # Fast path for macOS mirror windows (works even when not frontmost).
            image = self._capture_with_quartz()
            if image is not None:
                small_hash = str(compute_phash(image.resize((96, 170))))
                if self._prev_small_hash is not None and small_hash == self._prev_small_hash:
                    self._static_frame_streak += 1
                else:
                    self._static_frame_streak = 0
                self._prev_small_hash = small_hash

                # If Quartz feed appears frozen while stream is active, try
                # screencapture fallback to recover updates from background windows.
                if self._static_frame_streak < 10:
                    return image

            import tempfile

            # Create temp file for screenshot
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                temp_path = f.name

            # Try window ID capture first (fallback path)
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

            small_hash = str(compute_phash(image.resize((96, 170))))
            if self._prev_small_hash is not None and small_hash == self._prev_small_hash:
                self._static_frame_streak += 1
            else:
                self._static_frame_streak = 0
            self._prev_small_hash = small_hash
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
