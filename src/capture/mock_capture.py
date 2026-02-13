"""Mock capture for testing without a real device."""

from pathlib import Path
from typing import Iterator

import cv2
from PIL import Image

from src.capture.base import BaseCapture, DeviceInfo, DeviceType, ForegroundApp


class MockCapture(BaseCapture):
    """Mock capture that reads from video file or image directory."""

    def __init__(
        self,
        source: Path | str,
        loop: bool = True,
        instagram_mode: bool = True,
    ) -> None:
        """Initialize mock capture.

        Args:
            source: Path to video file or directory of images.
            loop: Whether to loop when reaching end of source.
            instagram_mode: Whether to simulate Instagram foreground.
        """
        self.source = Path(source)
        self.loop = loop
        self.instagram_mode = instagram_mode

        self._device_info = DeviceInfo(
            device_type=DeviceType.MOCK,
            device_id="mock-device",
            device_name="Mock Device",
            model="MockPhone",
            os_version="1.0",
        )

        self._connected = False
        self._frame_iterator: Iterator[Image.Image] | None = None
        self._video_capture: cv2.VideoCapture | None = None
        self._image_files: list[Path] = []
        self._current_index = 0

    @property
    def device_info(self) -> DeviceInfo:
        """Get device information."""
        return self._device_info

    @property
    def is_connected(self) -> bool:
        """Check if connected."""
        return self._connected

    def connect(self) -> bool:
        """Connect to the mock source."""
        if not self.source.exists():
            return False

        if self.source.is_file():
            # Video file
            self._video_capture = cv2.VideoCapture(str(self.source))
            if not self._video_capture.isOpened():
                return False
        elif self.source.is_dir():
            # Directory of images
            extensions = {".png", ".jpg", ".jpeg", ".bmp"}
            self._image_files = sorted(
                f for f in self.source.iterdir()
                if f.suffix.lower() in extensions
            )
            if not self._image_files:
                return False
            self._current_index = 0
        else:
            return False

        self._connected = True
        return True

    def disconnect(self) -> None:
        """Disconnect from mock source."""
        if self._video_capture:
            self._video_capture.release()
            self._video_capture = None

        self._image_files = []
        self._current_index = 0
        self._connected = False

    def capture_screen(self) -> Image.Image | None:
        """Get next frame from source."""
        if not self._connected:
            return None

        if self._video_capture:
            return self._capture_from_video()
        else:
            return self._capture_from_images()

    def _capture_from_video(self) -> Image.Image | None:
        """Capture frame from video."""
        if not self._video_capture:
            return None

        ret, frame = self._video_capture.read()

        if not ret:
            if self.loop:
                self._video_capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = self._video_capture.read()
                if not ret:
                    return None
            else:
                return None

        # Convert BGR to RGB
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        return Image.fromarray(frame_rgb)

    def _capture_from_images(self) -> Image.Image | None:
        """Capture from image sequence."""
        if not self._image_files:
            return None

        if self._current_index >= len(self._image_files):
            if self.loop:
                self._current_index = 0
            else:
                return None

        image_path = self._image_files[self._current_index]
        self._current_index += 1

        try:
            return Image.open(image_path).convert("RGB")
        except Exception:
            return None

    def get_foreground_app(self) -> ForegroundApp | None:
        """Get mock foreground app."""
        if not self._connected:
            return None

        if self.instagram_mode:
            return ForegroundApp(
                package_name="com.instagram.android",
                activity="com.instagram.reels.fragment.ReelsViewerFragment",
            )

        return ForegroundApp(
            package_name="com.mock.app",
            activity="MainActivity",
        )

    def set_instagram_mode(self, enabled: bool) -> None:
        """Toggle Instagram mode simulation.

        Args:
            enabled: Whether to simulate Instagram in foreground.
        """
        self.instagram_mode = enabled

    def get_frame_count(self) -> int:
        """Get total frame count for video source.

        Returns:
            Number of frames, or number of images.
        """
        if self._video_capture:
            return int(self._video_capture.get(cv2.CAP_PROP_FRAME_COUNT))
        return len(self._image_files)

    def get_fps(self) -> float:
        """Get FPS for video source.

        Returns:
            FPS value, or 1.0 for image sequences.
        """
        if self._video_capture:
            return self._video_capture.get(cv2.CAP_PROP_FPS)
        return 1.0
