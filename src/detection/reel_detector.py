"""Detect reel changes from screen captures."""

from dataclasses import dataclass
from enum import Enum, auto

from PIL import Image

from src.detection.image_utils import (
    compute_phash,
    extract_center_region,
    is_mostly_black,
    images_are_different,
)


class ReelChangeType(Enum):
    """Type of reel change detected."""

    NONE = auto()  # No change
    NEW_REEL = auto()  # Scrolled to new reel
    TRANSITION = auto()  # In transition/loading
    APP_CLOSED = auto()  # Left reels mode
    SESSION_START = auto()  # Entered Reels mode (content-based detection)
    SESSION_END = auto()  # Left Reels mode (content-based detection)


@dataclass
class ReelState:
    """Current state of reel detection."""

    current_hash: str | None = None
    previous_hash: str | None = None
    is_in_transition: bool = False
    consecutive_same_frames: int = 0
    last_screenshot: Image.Image | None = None


class ReelDetector:
    """Detect when user scrolls to a new reel."""

    def __init__(
        self,
        hash_threshold: int = 15,
        transition_frames: int = 3,
        stable_frames: int = 2,
    ) -> None:
        """Initialize reel detector.

        Args:
            hash_threshold: Minimum hash difference to consider a new reel.
            transition_frames: Number of frames to wait during transition.
            stable_frames: Number of same frames needed to confirm stable content.
        """
        self.hash_threshold = hash_threshold
        self.transition_frames = transition_frames
        self.stable_frames = stable_frames
        self._state = ReelState()

    @property
    def current_hash(self) -> str | None:
        """Get current frame hash."""
        return self._state.current_hash

    @property
    def last_screenshot(self) -> Image.Image | None:
        """Get last stable screenshot."""
        return self._state.last_screenshot

    def reset(self) -> None:
        """Reset detector state."""
        self._state = ReelState()

    def _compute_content_hash(self, frame: Image.Image) -> str:
        """Compute hash focusing on content area.

        Args:
            frame: Full screenshot.

        Returns:
            Hash string.
        """
        # Extract center region to focus on content, not UI
        content_region = extract_center_region(frame, width_ratio=0.9, height_ratio=0.7)
        hash_obj = compute_phash(content_region)
        return str(hash_obj)

    def _is_transition_frame(self, frame: Image.Image) -> bool:
        """Check if frame appears to be a transition (loading/scrolling).

        Args:
            frame: Frame to check.

        Returns:
            True if frame appears to be transitioning.
        """
        return is_mostly_black(frame, threshold=0.5)

    def process_frame(self, frame: Image.Image) -> ReelChangeType:
        """Process a new frame and detect reel changes.

        Args:
            frame: New screenshot frame.

        Returns:
            Type of change detected.
        """
        # Check for transition frame
        if self._is_transition_frame(frame):
            self._state.is_in_transition = True
            self._state.consecutive_same_frames = 0
            return ReelChangeType.TRANSITION

        # Compute hash for current frame
        current_hash = self._compute_content_hash(frame)

        # First frame initialization
        if self._state.current_hash is None:
            self._state.current_hash = current_hash
            self._state.last_screenshot = frame.copy()
            self._state.consecutive_same_frames = 1
            return ReelChangeType.NEW_REEL

        # Compare with current stable hash
        try:
            from imagehash import hex_to_hash

            current_hash_obj = hex_to_hash(current_hash)
            previous_hash_obj = hex_to_hash(self._state.current_hash)
            difference = current_hash_obj - previous_hash_obj
        except Exception:
            # Fallback: treat as different if comparison fails
            difference = self.hash_threshold + 1

        if difference <= self.hash_threshold:
            # Same content as before
            self._state.consecutive_same_frames += 1
            self._state.is_in_transition = False
            return ReelChangeType.NONE
        else:
            # Content changed
            if self._state.is_in_transition:
                # Coming out of transition with new content
                self._state.is_in_transition = False

            self._state.previous_hash = self._state.current_hash
            self._state.current_hash = current_hash
            self._state.last_screenshot = frame.copy()
            self._state.consecutive_same_frames = 1

            return ReelChangeType.NEW_REEL

    def is_stable(self) -> bool:
        """Check if current content appears stable (not scrolling).

        Returns:
            True if content has been stable for required frames.
        """
        return self._state.consecutive_same_frames >= self.stable_frames

    def get_stable_screenshot(self) -> Image.Image | None:
        """Get screenshot of stable content.

        Returns:
            Screenshot if content is stable, None otherwise.
        """
        if self.is_stable():
            return self._state.last_screenshot
        return None


class ReelSession:
    """Track a reel viewing session."""

    def __init__(self, detector: ReelDetector) -> None:
        """Initialize session.

        Args:
            detector: ReelDetector instance to use.
        """
        self.detector = detector
        self.reel_count = 0
        self.is_active = False

    def start(self) -> None:
        """Start a new session."""
        self.detector.reset()
        self.reel_count = 0
        self.is_active = True

    def stop(self) -> None:
        """Stop the current session."""
        self.is_active = False

    def process_frame(self, frame: Image.Image) -> tuple[ReelChangeType, int]:
        """Process frame and return change type and current reel number.

        Args:
            frame: Screenshot frame to process.

        Returns:
            Tuple of (change_type, current_reel_number).
        """
        if not self.is_active:
            return ReelChangeType.NONE, 0

        change_type = self.detector.process_frame(frame)

        if change_type == ReelChangeType.NEW_REEL:
            self.reel_count += 1

        return change_type, self.reel_count
