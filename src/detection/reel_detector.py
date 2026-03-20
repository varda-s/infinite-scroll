"""Detect reel changes from screen captures."""

from dataclasses import dataclass
from enum import Enum, auto

import cv2
import numpy as np
from PIL import Image

from src.detection.image_utils import (
    calculate_image_entropy,
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
    transition_quiet_frames: int = 0
    ui_signature: tuple[str, str] | None = None
    candidate_signature: tuple[str, str] | None = None
    candidate_hash: str | None = None
    candidate_count: int = 0
    previous_gray: np.ndarray | None = None
    last_motion_right: float = 0.0
    last_motion_center: float = 0.0
    last_vertical_shift: float = 0.0
    last_center_vertical_shift: float = 0.0
    last_icon_track_shift: float = 0.0
    last_icon_track_response: float = 0.0
    last_screenshot: Image.Image | None = None
    pending_screenshot: Image.Image | None = None
    transition_started_from_black: bool = False
    transition_frame_count: int = 0
    transition_peak_motion_right: float = 0.0
    transition_peak_motion_center: float = 0.0
    transition_peak_icon_shift: float = 0.0
    transition_peak_vertical_shift: float = 0.0
    transition_peak_center_vertical_shift: float = 0.0
    frame_index: int = 0
    last_new_reel_frame: int = -9999
    last_scroll_frame: int = -9999
    scroll_direction: int = 0
    scroll_direction_frames: int = 0
    cooldown_until_frame: int = 0
    waiting_for_post_reel_stable: bool = False
    post_reel_stable_frames: int = 0


class ReelDetector:
    """Detect when user scrolls to a new reel."""

    def __init__(
        self,
        hash_threshold: int = 15,
        transition_frames: int = 3,
        stable_frames: int = 2,
        new_reel_cooldown_frames: int = 22,
        post_reel_stable_release_frames: int = 4,
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
        # Thresholds tuned from observed Instagram reel scroll dynamics.
        self.swipe_motion_right_threshold = 4.5
        self.swipe_motion_center_threshold = 7.0
        self.swipe_vertical_shift_threshold = 2.0
        self.swipe_center_vertical_shift_threshold = 3.5
        self.icon_track_shift_threshold = 4.0
        self.icon_track_min_response = 0.35
        self.settle_motion_right_threshold = 7.5
        self.settle_motion_center_threshold = 8.5
        self.signature_change_threshold = 8
        # Prevent duplicate NEW_REEL bursts from a single swipe.
        self.min_new_reel_gap_frames = 8
        self.new_reel_cooldown_frames = new_reel_cooldown_frames
        self.post_reel_stable_release_frames = post_reel_stable_release_frames
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

    def _compute_ui_signature(self, frame: Image.Image) -> tuple[str, str]:
        """Compute signature from UI regions that change between reels."""
        width, height = frame.size
        # Focus on overlay masks rather than raw pixels so video-content motion
        # contributes less to the signature than the fixed Instagram UI chrome.
        right = frame.crop(
            (
                int(width * 0.81),
                int(height * 0.24),
                int(width * 0.95),
                int(height * 0.90),
            )
        )
        bottom = frame.crop(
            (
                int(width * 0.04),
                int(height * 0.76),
                int(width * 0.78),
                int(height * 0.94),
            )
        )

        right_mask = self._ui_overlay_mask(right, size=(80, 200))
        bottom_mask = self._ui_overlay_mask(bottom, size=(240, 80))
        return (str(compute_phash(right_mask, hash_size=12)), str(compute_phash(bottom_mask, hash_size=12)))

    def _ui_overlay_mask(self, region: Image.Image, size: tuple[int, int]) -> Image.Image:
        """Extract a coarse binary mask of bright UI overlay elements."""
        gray = np.array(region.convert("L").resize(size, Image.Resampling.BILINEAR))
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        # Instagram reel UI text/icons are usually high-contrast overlay glyphs.
        _, mask = cv2.threshold(blur, 150, 255, cv2.THRESH_BINARY)
        return Image.fromarray(mask)

    def _signature_distance(
        self, sig1: tuple[str, str] | None, sig2: tuple[str, str] | None
    ) -> int:
        """Compute Hamming-like distance between two UI signatures."""
        if sig1 is None or sig2 is None:
            return 64
        try:
            from imagehash import hex_to_hash

            return (hex_to_hash(sig1[0]) - hex_to_hash(sig2[0])) + (
                hex_to_hash(sig1[1]) - hex_to_hash(sig2[1])
            )
        except Exception:
            return 64

    def _single_hash_distance(self, h1: str | None, h2: str | None) -> int:
        """Compute hash distance for a single hex hash string."""
        if not h1 or not h2:
            return 64
        try:
            from imagehash import hex_to_hash

            return int(hex_to_hash(h1) - hex_to_hash(h2))
        except Exception:
            return 64

    def _hash_distance(self, h1: str | None, h2: str | None) -> int:
        """Compute pHash distance between two hash strings."""
        if not h1 or not h2:
            return 64
        try:
            from imagehash import hex_to_hash

            return int(hex_to_hash(h1) - hex_to_hash(h2))
        except Exception:
            return 64

    def _is_reel_change(self, new_sig: tuple[str, str], current_hash: str) -> bool:
        """Decide whether settled content truly represents a new reel."""
        old_sig = self._state.ui_signature
        right_diff = self._single_hash_distance(
            new_sig[0], old_sig[0] if old_sig else None
        )
        bottom_diff = self._single_hash_distance(
            new_sig[1], old_sig[1] if old_sig else None
        )
        content_diff = self._hash_distance(current_hash, self._state.current_hash)

        # Primary signal: both stable UI anchor regions changed.
        if right_diff >= 4 and bottom_diff >= 4:
            return True
        # Strong right-rail change is often enough on its own.
        if right_diff >= 7:
            return True
        # Bottom/caption drift needs backing from content drift.
        if bottom_diff >= 8 and content_diff >= 10:
            return True
        # Conservative fallback: moderate UI drift plus strong content shift.
        if right_diff >= 3 and bottom_diff >= 5 and content_diff >= 12:
            return True
        return False

    def _same_signature(
        self,
        sig1: tuple[str, str] | None,
        sig2: tuple[str, str] | None,
        tolerance: int = 2,
    ) -> bool:
        """Return True when two UI signatures are effectively the same reel."""
        if sig1 is None or sig2 is None:
            return False
        right_diff = self._single_hash_distance(sig1[0], sig2[0])
        bottom_diff = self._single_hash_distance(sig1[1], sig2[1])
        return right_diff <= tolerance and bottom_diff <= tolerance

    def _reset_candidate(self) -> None:
        self._state.candidate_signature = None
        self._state.candidate_hash = None
        self._state.candidate_count = 0
        self._state.pending_screenshot = None

    def _confirm_candidate_reel(
        self,
        frame: Image.Image,
        current_hash: str,
        new_sig: tuple[str, str],
    ) -> ReelChangeType:
        """Confirm a new reel from stable UI signatures."""
        if self._same_signature(new_sig, self._state.ui_signature):
            self._reset_candidate()
            self._state.last_screenshot = frame.copy()
            self._state.consecutive_same_frames += 1
            return ReelChangeType.NONE

        if not self._is_reel_change(new_sig, current_hash):
            self._reset_candidate()
            self._state.last_screenshot = frame.copy()
            self._state.consecutive_same_frames += 1
            return ReelChangeType.NONE

        if self._same_signature(new_sig, self._state.candidate_signature):
            self._state.candidate_count += 1
        else:
            self._state.candidate_signature = new_sig
            self._state.candidate_hash = current_hash
            self._state.candidate_count = 1
            self._state.pending_screenshot = frame.copy()

        if self._state.candidate_count < self.stable_frames:
            self._state.consecutive_same_frames += 1
            return ReelChangeType.NONE

        self._state.previous_hash = self._state.current_hash
        self._state.current_hash = self._state.candidate_hash or current_hash
        self._state.ui_signature = self._state.candidate_signature or new_sig
        self._state.last_screenshot = self._state.pending_screenshot or frame.copy()
        self._state.is_in_transition = False
        self._state.transition_started_from_black = False
        self._state.transition_quiet_frames = 0
        self._state.transition_frame_count = 0
        self._state.transition_peak_motion_right = 0.0
        self._state.transition_peak_motion_center = 0.0
        self._state.transition_peak_icon_shift = 0.0
        self._state.transition_peak_vertical_shift = 0.0
        self._state.transition_peak_center_vertical_shift = 0.0
        self._state.consecutive_same_frames = 1
        self._reset_candidate()
        if self._can_emit_new_reel():
            self._state.waiting_for_post_reel_stable = True
            self._state.post_reel_stable_frames = 0
            return ReelChangeType.NEW_REEL
        return ReelChangeType.NONE

    def _estimate_vertical_shift(self, prev: np.ndarray, curr: np.ndarray) -> float:
        """Estimate dominant vertical shift via row-profile cross correlation."""
        if prev.size == 0 or curr.size == 0:
            return 0.0
        p = prev.mean(axis=1).astype(np.float32)
        c = curr.mean(axis=1).astype(np.float32)
        p -= p.mean()
        c -= c.mean()
        if np.allclose(p, 0) or np.allclose(c, 0):
            return 0.0
        corr = np.correlate(c, p, mode="full")
        lag = int(np.argmax(corr) - (len(p) - 1))
        return float(lag)

    def _can_emit_new_reel(self) -> bool:
        """Prevent duplicate NEW_REEL bursts during one swipe transition."""
        if self._state.frame_index < self._state.cooldown_until_frame:
            return False
        if self._state.frame_index - self._state.last_new_reel_frame < self.min_new_reel_gap_frames:
            return False
        self._state.last_new_reel_frame = self._state.frame_index
        self._state.cooldown_until_frame = self._state.frame_index + self.new_reel_cooldown_frames
        return True

    def _has_recent_scroll_gesture(self, max_age_frames: int = 8) -> bool:
        """Return True if a vertical swipe-like motion was seen recently."""
        return (self._state.frame_index - self._state.last_scroll_frame) <= max_age_frames

    def _compute_motion_metrics(self, frame: Image.Image) -> tuple[float, float, float, float, float, float]:
        """Compute right/center motion and vertical shifts."""
        gray = np.array(frame.convert("L").resize((216, 468), Image.Resampling.BILINEAR))
        prev = self._state.previous_gray
        self._state.previous_gray = gray

        if prev is None:
            return 0.0, 0.0, 0.0, 0.0, 0.0, 0.0

        w = gray.shape[1]
        right_slice = slice(int(w * 0.76), w)
        center_slice = slice(int(w * 0.20), int(w * 0.80))

        right = gray[:, right_slice]
        prev_right = prev[:, right_slice]
        center = gray[:, center_slice]
        prev_center = prev[:, center_slice]

        motion_right = float(np.mean(np.abs(right.astype(np.int16) - prev_right.astype(np.int16))))
        motion_center = float(np.mean(np.abs(center.astype(np.int16) - prev_center.astype(np.int16))))
        vertical_shift = self._estimate_vertical_shift(prev_right, right)
        center_vertical_shift = self._estimate_vertical_shift(prev_center, center)
        icon_track_shift = 0.0
        icon_track_response = 0.0
        try:
            # Icon-focused tracking: isolate bright UI glyphs/text in the
            # right interaction rail so video-content motion contributes less.
            prev_mask = (prev_right >= 170).astype(np.float32)
            curr_mask = (right >= 170).astype(np.float32)
            if float(prev_mask.mean()) >= 0.01 and float(curr_mask.mean()) >= 0.01:
                (_dx, dy), response = cv2.phaseCorrelate(prev_mask, curr_mask)
            else:
                (_dx, dy), response = cv2.phaseCorrelate(
                    prev_right.astype(np.float32), right.astype(np.float32)
                )
            icon_track_shift = abs(float(dy))
            icon_track_response = float(response)
        except Exception:
            pass

        self._state.last_motion_right = motion_right
        self._state.last_motion_center = motion_center
        self._state.last_vertical_shift = vertical_shift
        self._state.last_center_vertical_shift = center_vertical_shift
        self._state.last_icon_track_shift = icon_track_shift
        self._state.last_icon_track_response = icon_track_response
        return (
            motion_right,
            motion_center,
            vertical_shift,
            center_vertical_shift,
            icon_track_shift,
            icon_track_response,
        )

    def _is_transition_frame(self, frame: Image.Image) -> bool:
        """Check if frame appears to be a transition (loading/scrolling).

        Args:
            frame: Frame to check.

        Returns:
            True if frame appears to be transitioning.
        """
        # Use only center content and require both high darkness and very low
        # entropy. This avoids false transition loops on dark reels.
        center = extract_center_region(frame, width_ratio=0.6, height_ratio=0.65)
        return is_mostly_black(center, threshold=0.88) and calculate_image_entropy(center) < 2.0

    def process_frame(self, frame: Image.Image) -> ReelChangeType:
        """Process a new frame and detect reel changes.

        Args:
            frame: New screenshot frame.

        Returns:
            Type of change detected.
        """
        self._state.frame_index += 1
        (
            motion_right,
            motion_center,
            vertical_shift,
            center_vertical_shift,
            icon_track_shift,
            icon_track_response,
        ) = self._compute_motion_metrics(frame)
        settled_now = (
            motion_right <= self.settle_motion_right_threshold
            and motion_center <= self.settle_motion_center_threshold
        )

        # After counting a new reel, require a short stable window before
        # allowing another transition. This suppresses double/triple counts
        # caused by one physical swipe producing multiple transition bursts.
        if self._state.waiting_for_post_reel_stable:
            if settled_now:
                self._state.post_reel_stable_frames += 1
            else:
                self._state.post_reel_stable_frames = 0

            if self._state.post_reel_stable_frames < self.post_reel_stable_release_frames:
                self._state.consecutive_same_frames += 1
                return ReelChangeType.NONE

            self._state.waiting_for_post_reel_stable = False
            self._state.post_reel_stable_frames = 0

        # Track coherent vertical scroll direction to reject random motion bursts.
        dominant_shift = (
            center_vertical_shift
            if abs(center_vertical_shift) >= abs(vertical_shift)
            else vertical_shift
        )
        if abs(dominant_shift) >= 2.0:
            direction = 1 if dominant_shift > 0 else -1
            if direction == self._state.scroll_direction:
                self._state.scroll_direction_frames += 1
            else:
                self._state.scroll_direction = direction
                self._state.scroll_direction_frames = 1
        else:
            self._state.scroll_direction = 0
            self._state.scroll_direction_frames = 0

        # Only count new reels when we have evidence of user scroll gesture.
        if self._state.scroll_direction_frames >= 2 and (
            (
                icon_track_shift >= self.icon_track_shift_threshold
                and icon_track_response >= self.icon_track_min_response
                and motion_right >= 5.0
                and (
                    abs(center_vertical_shift) >= 2.0
                    or abs(vertical_shift) >= 1.5
                )
            )
            or (
                abs(center_vertical_shift) >= self.swipe_center_vertical_shift_threshold
                and motion_center >= 6.0
            )
            or (
                abs(vertical_shift) >= self.swipe_vertical_shift_threshold
                and motion_center >= 6.0
            )
        ):
            self._state.last_scroll_frame = self._state.frame_index

        # Track peak motion while transition is active.
        if self._state.is_in_transition:
            self._state.transition_peak_motion_right = max(
                self._state.transition_peak_motion_right, motion_right
            )
            self._state.transition_peak_motion_center = max(
                self._state.transition_peak_motion_center, motion_center
            )
            self._state.transition_peak_icon_shift = max(
                self._state.transition_peak_icon_shift, icon_track_shift
            )
            self._state.transition_peak_vertical_shift = max(
                self._state.transition_peak_vertical_shift,
                abs(vertical_shift),
            )
            self._state.transition_peak_center_vertical_shift = max(
                self._state.transition_peak_center_vertical_shift,
                abs(center_vertical_shift),
            )

        # Treat near-black frames as transition only if a swipe transition is
        # already active; dark reels should not start transitions by themselves.
        if self._state.is_in_transition and self._is_transition_frame(frame):
            self._state.transition_started_from_black = True
            self._state.transition_quiet_frames = 0
            self._reset_candidate()
            self._state.consecutive_same_frames = 0
            return ReelChangeType.TRANSITION

        # Compute hash for current frame
        current_hash = self._compute_content_hash(frame)

        # First frame initialization
        if self._state.current_hash is None:
            self._state.current_hash = current_hash
            self._state.ui_signature = self._compute_ui_signature(frame)
            self._state.last_screenshot = frame.copy()
            self._state.consecutive_same_frames = 1
            return ReelChangeType.NEW_REEL if self._can_emit_new_reel() else ReelChangeType.NONE
        new_sig = self._compute_ui_signature(frame)
        if self._state.is_in_transition:
            self._state.transition_frame_count += 1

            settled = (
                motion_right <= self.settle_motion_right_threshold
                and motion_center <= self.settle_motion_center_threshold
            )
            if settled:
                self._state.transition_quiet_frames += 1
                # Use one of the first stable frames of the new reel.
                if self._state.pending_screenshot is None:
                    self._state.pending_screenshot = frame.copy()
            else:
                self._state.transition_quiet_frames = 0
                self._reset_candidate()

            transition_was_real_swipe = (
                self._state.transition_peak_motion_right >= 6.0
                and self._state.transition_peak_motion_center >= 7.0
                and (
                    self._state.transition_peak_center_vertical_shift >= 3.0
                    or self._state.transition_peak_vertical_shift >= 2.0
                    or self._state.transition_peak_icon_shift >= 4.0
                )
                and self._has_recent_scroll_gesture(max_age_frames=60)
            )

            if settled and transition_was_real_swipe:
                return self._confirm_candidate_reel(frame, current_hash, new_sig)

            if self._state.transition_quiet_frames >= self.transition_frames:
                self._state.is_in_transition = False
                self._state.transition_started_from_black = False
                self._state.transition_quiet_frames = 0
                self._state.transition_frame_count = 0
                self._state.consecutive_same_frames = 1
                self._reset_candidate()
                self._state.transition_peak_motion_right = 0.0
                self._state.transition_peak_motion_center = 0.0
                self._state.transition_peak_icon_shift = 0.0
                self._state.transition_peak_vertical_shift = 0.0
                self._state.transition_peak_center_vertical_shift = 0.0
                return ReelChangeType.NONE

            # Escape hatch: avoid getting stuck in transition state forever due
            # noisy motion. After a short timeout, decide using hash/signature.
            if self._state.transition_frame_count >= 10:
                self._state.is_in_transition = False
                self._state.transition_started_from_black = False
                self._state.transition_quiet_frames = 0
                self._state.transition_frame_count = 0
                self._state.consecutive_same_frames = 1
                self._reset_candidate()
                self._state.transition_peak_motion_right = 0.0
                self._state.transition_peak_motion_center = 0.0
                self._state.transition_peak_icon_shift = 0.0
                self._state.transition_peak_vertical_shift = 0.0
                self._state.transition_peak_center_vertical_shift = 0.0
                return ReelChangeType.NONE

            return ReelChangeType.TRANSITION

        # Stable frames can still reveal a new reel even if explicit motion
        # tracking missed the swipe onset; confirm via fixed UI regions.
        if settled_now and self._has_recent_scroll_gesture(max_age_frames=max(18, self.new_reel_cooldown_frames)):
            return self._confirm_candidate_reel(frame, current_hash, new_sig)
        self._reset_candidate()

        # Detect swipe onset from motion burst: right icon rail moves with content.
        # This must run only when we're not already in transition; otherwise
        # transition counters get reset every frame and NEW_REEL is never emitted.
        swipe_motion = (
            (
                (
                    motion_right >= self.swipe_motion_right_threshold
                    and motion_center >= self.swipe_motion_center_threshold
                )
                or abs(center_vertical_shift)
                >= (self.swipe_center_vertical_shift_threshold + 1.0)
            )
            and (
                (
                    icon_track_shift >= self.icon_track_shift_threshold
                    and icon_track_response >= self.icon_track_min_response
                )
                or abs(vertical_shift) >= self.swipe_vertical_shift_threshold
                or abs(center_vertical_shift) >= self.swipe_center_vertical_shift_threshold
            )
            and self._state.scroll_direction_frames >= 2
        )
        if swipe_motion:
            self._state.is_in_transition = True
            self._state.transition_started_from_black = False
            self._state.transition_quiet_frames = 0
            self._state.transition_frame_count = 0
            self._state.transition_peak_motion_right = motion_right
            self._state.transition_peak_motion_center = motion_center
            self._state.transition_peak_icon_shift = icon_track_shift
            self._state.transition_peak_vertical_shift = abs(vertical_shift)
            self._state.transition_peak_center_vertical_shift = abs(center_vertical_shift)
            self._state.consecutive_same_frames = 0
            self._state.pending_screenshot = None
            return ReelChangeType.TRANSITION

        # No transition and no confirmed swipe completion.
        # Stable in-reel browsing: no transition, no new reel.
        self._state.consecutive_same_frames += 1
        return ReelChangeType.NONE

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
