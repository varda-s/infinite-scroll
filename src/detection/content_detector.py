"""Content-based detection for Instagram Reels mode.

This module provides content analysis to detect when the user is viewing
Instagram Reels, enabling automatic session start/end detection without
relying on app-level signals (which aren't available in mirror mode).
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

import numpy as np
from PIL import Image

from src.detection.image_utils import (
    calculate_image_entropy,
    compute_phash,
    is_mostly_black,
)


class ContentType(Enum):
    """Type of content detected on screen."""

    UNKNOWN = auto()  # Cannot determine content type
    REELS = auto()  # Instagram Reels (vertical video)
    STATIC_UI = auto()  # Static UI (home screen, settings, etc.)
    BLACK_SCREEN = auto()  # Screen is black/locked
    TRANSITION = auto()  # Content is transitioning


@dataclass
class ContentState:
    """Current state of content detection."""

    content_type: ContentType = ContentType.UNKNOWN
    confidence: float = 0.0
    last_hash: Optional[str] = None
    consecutive_reels_frames: int = 0
    consecutive_non_reels_frames: int = 0
    in_reels_session: bool = False
    black_frame_count: int = 0


@dataclass
class ContentAnalysis:
    """Result of analyzing a single frame's content."""

    content_type: ContentType
    confidence: float
    aspect_ratio: float
    entropy: float
    is_vertical_video: bool
    hash_value: str


class ContentDetector:
    """Detect Instagram Reels mode based on screen content analysis.

    This detector analyzes screen captures to determine:
    1. If the user is viewing Instagram Reels (vertical video content)
    2. When a session starts (entering Reels mode)
    3. When a session ends (leaving Reels mode)

    Detection is based on:
    - Aspect ratio (Reels are 9:16 vertical videos)
    - Content entropy (videos have high entropy vs static UI)
    - Content stability patterns
    - Dramatic hash changes (indicating app/mode changes)
    """

    # Thresholds for detection
    MIN_ENTROPY_FOR_VIDEO = 5.0  # Minimum entropy to consider as video content
    MIN_VERTICAL_RATIO = 1.5  # Minimum height/width ratio for vertical content
    MAX_VERTICAL_RATIO = 2.5  # Maximum reasonable ratio (phone screen)
    DRAMATIC_HASH_THRESHOLD = 40  # Hash diff indicating major content change
    REELS_CONFIRMATION_FRAMES = 3  # Frames needed to confirm Reels mode
    NON_REELS_CONFIRMATION_FRAMES = 5  # Frames needed to confirm leaving Reels
    BLACK_SCREEN_THRESHOLD = 3  # Black frames before considering screen locked

    def __init__(
        self,
        reels_confirmation_frames: int = 3,
        non_reels_confirmation_frames: int = 5,
        hash_threshold: int = 15,
    ) -> None:
        """Initialize content detector.

        Args:
            reels_confirmation_frames: Frames needed to confirm entering Reels.
            non_reels_confirmation_frames: Frames needed to confirm leaving Reels.
            hash_threshold: Normal hash difference threshold for same content.
        """
        self.reels_confirmation_frames = reels_confirmation_frames
        self.non_reels_confirmation_frames = non_reels_confirmation_frames
        self.hash_threshold = hash_threshold
        self._state = ContentState()

    @property
    def in_reels_session(self) -> bool:
        """Check if currently in a Reels viewing session."""
        return self._state.in_reels_session

    @property
    def current_content_type(self) -> ContentType:
        """Get the current detected content type."""
        return self._state.content_type

    def reset(self) -> None:
        """Reset detector state."""
        self._state = ContentState()

    def _analyze_aspect_ratio(self, image: Image.Image) -> tuple[float, bool]:
        """Analyze if image has vertical video aspect ratio.

        Args:
            image: Image to analyze.

        Returns:
            Tuple of (aspect_ratio, is_vertical_video).
        """
        width, height = image.size
        aspect_ratio = height / width if width > 0 else 0

        is_vertical = self.MIN_VERTICAL_RATIO <= aspect_ratio <= self.MAX_VERTICAL_RATIO
        return aspect_ratio, is_vertical

    def _analyze_content_region(self, image: Image.Image) -> tuple[float, bool]:
        """Analyze the content region for video-like characteristics.

        Args:
            image: Image to analyze.

        Returns:
            Tuple of (entropy, is_video_like).
        """
        # Focus on center region (where video content is)
        width, height = image.size
        left = int(width * 0.1)
        right = int(width * 0.9)
        top = int(height * 0.15)
        bottom = int(height * 0.85)

        content_region = image.crop((left, top, right, bottom))
        entropy = calculate_image_entropy(content_region)

        is_video_like = entropy >= self.MIN_ENTROPY_FOR_VIDEO
        return entropy, is_video_like

    def _compute_hash(self, image: Image.Image) -> str:
        """Compute perceptual hash of image.

        Args:
            image: Image to hash.

        Returns:
            Hash string.
        """
        hash_obj = compute_phash(image)
        return str(hash_obj)

    def _compare_hashes(self, hash1: str, hash2: str) -> int:
        """Compare two hash strings.

        Args:
            hash1: First hash.
            hash2: Second hash.

        Returns:
            Hamming distance between hashes.
        """
        try:
            from imagehash import hex_to_hash

            h1 = hex_to_hash(hash1)
            h2 = hex_to_hash(hash2)
            return h1 - h2
        except Exception:
            return self.DRAMATIC_HASH_THRESHOLD + 1

    def analyze_frame(self, frame: Image.Image) -> ContentAnalysis:
        """Analyze a single frame's content.

        Args:
            frame: Screenshot frame to analyze.

        Returns:
            ContentAnalysis with detected content characteristics.
        """
        # Check for black screen first
        if is_mostly_black(frame, threshold=0.7):
            return ContentAnalysis(
                content_type=ContentType.BLACK_SCREEN,
                confidence=0.9,
                aspect_ratio=0.0,
                entropy=0.0,
                is_vertical_video=False,
                hash_value=self._compute_hash(frame),
            )

        # Analyze aspect ratio
        aspect_ratio, is_vertical = self._analyze_aspect_ratio(frame)

        # Analyze content entropy
        entropy, is_video_like = self._analyze_content_region(frame)

        # Compute hash for comparison
        hash_value = self._compute_hash(frame)

        # Determine content type
        if is_vertical and is_video_like:
            content_type = ContentType.REELS
            confidence = min(0.9, 0.5 + (entropy - self.MIN_ENTROPY_FOR_VIDEO) * 0.1)
        elif is_vertical and not is_video_like:
            # Vertical but low entropy - might be static screen in Reels
            content_type = ContentType.STATIC_UI
            confidence = 0.6
        else:
            content_type = ContentType.STATIC_UI
            confidence = 0.7

        return ContentAnalysis(
            content_type=content_type,
            confidence=confidence,
            aspect_ratio=aspect_ratio,
            entropy=entropy,
            is_vertical_video=is_vertical and is_video_like,
            hash_value=hash_value,
        )

    def process_frame(self, frame: Image.Image) -> tuple[ContentType, bool, bool]:
        """Process a frame and detect session state changes.

        Args:
            frame: Screenshot frame to process.

        Returns:
            Tuple of (content_type, session_started, session_ended).
            - content_type: Detected content type
            - session_started: True if this frame triggered session start
            - session_ended: True if this frame triggered session end
        """
        analysis = self.analyze_frame(frame)
        session_started = False
        session_ended = False

        # Handle black screen
        if analysis.content_type == ContentType.BLACK_SCREEN:
            self._state.black_frame_count += 1
            if (
                self._state.in_reels_session
                and self._state.black_frame_count >= self.BLACK_SCREEN_THRESHOLD
            ):
                # Screen locked while in session
                session_ended = True
                self._state.in_reels_session = False
                self._state.consecutive_reels_frames = 0
            self._state.content_type = ContentType.BLACK_SCREEN
            return ContentType.BLACK_SCREEN, session_started, session_ended

        # Reset black frame counter
        self._state.black_frame_count = 0

        # Check for dramatic content change
        if self._state.last_hash is not None:
            hash_diff = self._compare_hashes(analysis.hash_value, self._state.last_hash)
            if hash_diff >= self.DRAMATIC_HASH_THRESHOLD:
                # Major content change - might be leaving app
                if (
                    self._state.in_reels_session
                    and analysis.content_type != ContentType.REELS
                ):
                    self._state.consecutive_non_reels_frames += 1

        self._state.last_hash = analysis.hash_value

        # Update frame counters based on content type
        if analysis.content_type == ContentType.REELS:
            self._state.consecutive_reels_frames += 1
            self._state.consecutive_non_reels_frames = 0

            # Check if we should start a session
            if (
                not self._state.in_reels_session
                and self._state.consecutive_reels_frames >= self.reels_confirmation_frames
            ):
                session_started = True
                self._state.in_reels_session = True
        else:
            self._state.consecutive_non_reels_frames += 1
            self._state.consecutive_reels_frames = 0

            # Check if we should end a session
            if (
                self._state.in_reels_session
                and self._state.consecutive_non_reels_frames
                >= self.non_reels_confirmation_frames
            ):
                session_ended = True
                self._state.in_reels_session = False

        self._state.content_type = analysis.content_type
        return analysis.content_type, session_started, session_ended

    def is_reels_content(self, frame: Image.Image) -> bool:
        """Quick check if frame appears to be Reels content.

        Args:
            frame: Frame to check.

        Returns:
            True if frame appears to be Reels content.
        """
        analysis = self.analyze_frame(frame)
        return analysis.content_type == ContentType.REELS
