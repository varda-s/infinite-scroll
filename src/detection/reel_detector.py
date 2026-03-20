"""Detect reel changes from mirrored screen captures using optical-flow events."""

from __future__ import annotations

import logging
import queue
import threading
from collections import deque
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from src.detection.image_utils import compute_phash


logger = logging.getLogger(__name__)


class ReelChangeType(Enum):
    """Type of reel change detected."""

    NONE = auto()  # No change
    NEW_REEL = auto()  # Scrolled to new reel
    TRANSITION = auto()  # In transition/loading
    APP_CLOSED = auto()  # Left reels mode
    SESSION_START = auto()  # Entered Reels mode (content-based detection)
    SESSION_END = auto()  # Left Reels mode (content-based detection)


class DetectorMode(Enum):
    """Internal state machine modes."""

    IDLE = "IDLE"
    TRANSITION = "TRANSITION"
    SETTLING = "SETTLING"
    COOLDOWN = "COOLDOWN"


@dataclass
class ReelDetectorConfig:
    """Configurable settings for optical-flow reel change detection."""

    analysis_width: int = 360
    analysis_height: int = 640
    expected_fps: float = 30.0

    roi_x1: float = 0.15
    roi_y1: float = 0.15
    roi_x2: float = 0.85
    roi_y2: float = 0.85

    # UI regions that tend to change between reels while center video content can
    # animate independently. These are used for final reel confirmation hashes.
    ui_right_x1: float = 0.76
    ui_right_y1: float = 0.14
    ui_right_x2: float = 0.98
    ui_right_y2: float = 0.90
    ui_bottom_x1: float = 0.04
    ui_bottom_y1: float = 0.70
    ui_bottom_x2: float = 0.96
    ui_bottom_y2: float = 0.96

    motion_mag_thresh: float = 1.0
    trigger_mean_vy: float = 0.85
    trigger_vertical_ratio: float = 1.45
    trigger_coverage: float = 0.24
    trigger_consistency: float = 0.55
    trigger_consecutive_frames: int = 2
    weak_trigger_consecutive_frames: int = 6
    impulse_trigger_mean_vy: float = 1.75
    impulse_trigger_vertical_ratio: float = 1.15
    impulse_trigger_coverage: float = 0.28
    impulse_trigger_consistency: float = 0.45
    min_transition_displacement_px: float = 10.0
    rearm_settle_frames: int = 3

    settle_mean_mag: float = 3.0
    settle_consecutive_frames: int = 7
    auto_calibrate_settle: bool = True
    settle_multiplier: float = 1.20
    settle_history_size: int = 180

    min_transition_ms: int = 80
    max_transition_ms: int = 1200
    cooldown_ms: int = 900
    min_confirmed_gap_ms: int = 900

    phash_hamming_min_new_reel: int = 10
    ui_phash_hamming_min_new_reel: int = 6

    ring_buffer_size: int = 120

    # Best-frame selection defaults.
    best_frame_lookback: int = 10
    blur_laplacian_min: float = 45.0
    brightness_min: float = 35.0
    brightness_max: float = 220.0

    # Logging cadence. 1 means every frame.
    metric_log_interval_frames: int = 1

    # Async saver settings.
    save_output_dir: Path = field(default_factory=lambda: Path("output") / "reel_screenshots")
    save_png: bool = True


@dataclass
class FlowFeatures:
    """Optical-flow features extracted per frame pair."""

    mean_abs_vx: float = 0.0
    mean_abs_vy: float = 0.0
    vertical_ratio: float = 0.0
    coverage: float = 0.0
    median_vy: float = 0.0
    direction_consistency: float = 0.0
    mean_mag: float = 0.0


@dataclass
class BufferedFrame:
    """Frame record for best-frame selection."""

    timestamp_ms: float
    frame_bgr: np.ndarray
    mean_mag: float
    laplacian_var: float
    brightness: float


@dataclass
class _SaveRequest:
    path: Path
    frame_bgr: np.ndarray


@dataclass
class ReelState:
    """Current state of reel detection."""

    # Compatibility/publicly read by tests and call sites.
    current_hash: str | None = None
    previous_hash: str | None = None
    last_screenshot: Image.Image | None = None
    pending_screenshot: Image.Image | None = None
    consecutive_same_frames: int = 0
    frame_index: int = 0
    is_in_transition: bool = False

    # New state-machine fields.
    mode: DetectorMode = DetectorMode.IDLE
    trigger_streak: int = 0
    weak_trigger_streak: int = 0
    settle_streak: int = 0
    transition_started_at_frame: int = 0
    cooldown_until_frame: int = 0
    previous_roi_gray: np.ndarray | None = None
    last_features: FlowFeatures = field(default_factory=FlowFeatures)
    motion_floor_ema: float = 0.0
    transition_cumulative_vy: float = 0.0
    armed_for_transition: bool = True
    last_confirmed_frame: int = 0


class AsyncScreenshotSaver:
    """Write screenshots asynchronously to avoid detector-loop stalls."""

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._queue: queue.Queue[_SaveRequest] = queue.Queue(maxsize=256)
        self._stop_event = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name="reel-saver",
            daemon=True,
        )
        self._thread.start()

    def submit(self, path: Path, frame_bgr: np.ndarray) -> None:
        try:
            self._queue.put_nowait(_SaveRequest(path=path, frame_bgr=frame_bgr.copy()))
        except queue.Full:
            logger.warning("screenshot_save_dropped reason=queue_full path=%s", path)

    def close(self, timeout_s: float = 2.0) -> None:
        self._stop_event.set()
        self._thread.join(timeout=timeout_s)

    def _run(self) -> None:
        while not self._stop_event.is_set() or not self._queue.empty():
            try:
                task = self._queue.get(timeout=0.1)
            except queue.Empty:
                continue

            try:
                task.path.parent.mkdir(parents=True, exist_ok=True)
                ok = cv2.imwrite(str(task.path), task.frame_bgr)
                if ok:
                    logger.info("screenshot_saved path=%s", task.path)
                else:
                    logger.warning("screenshot_save_failed path=%s", task.path)
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.exception("screenshot_save_exception path=%s err=%r", task.path, exc)
            finally:
                self._queue.task_done()


class ReelDetector:
    """Detect when user swipes to a new reel via dense optical flow."""

    def __init__(
        self,
        hash_threshold: int = 15,
        transition_frames: int = 3,
        stable_frames: int = 2,
        detector_config: ReelDetectorConfig | None = None,
        output_dir: Path | None = None,
        save_screenshots: bool = False,
    ) -> None:
        """Initialize reel detector.

        Args:
            hash_threshold: Backward-compatible dedupe threshold override.
            transition_frames: Backward-compatible trigger streak override.
            stable_frames: Number of stable frames for `is_stable()` API.
            detector_config: Optional full detector config.
            output_dir: Optional output directory for async screenshot writing.
            save_screenshots: Enable async screenshot writing.
        """
        self.hash_threshold = hash_threshold
        self.transition_frames = transition_frames
        self.stable_frames = stable_frames

        self.config = detector_config or ReelDetectorConfig()
        # Preserve old constructor semantics while keeping config tunable.
        self.config.trigger_consecutive_frames = max(1, int(transition_frames))
        self.config.phash_hamming_min_new_reel = int(hash_threshold)

        if output_dir is not None:
            self.config.save_output_dir = Path(output_dir) / "reel_screenshots"

        # Compatibility attributes used in older tests.
        self.swipe_motion_right_threshold = self.config.trigger_mean_vy
        self.swipe_motion_center_threshold = self.config.trigger_mean_vy
        self.settle_motion_right_threshold = self.config.settle_mean_mag
        self.settle_motion_center_threshold = self.config.settle_mean_mag

        self._state = ReelState()
        self._ring_buffer: deque[BufferedFrame] = deque(maxlen=self.config.ring_buffer_size)
        self._idle_motion_history: deque[float] = deque(maxlen=self.config.settle_history_size)
        self._saved_reel_count = 0
        self._last_saved_phash: str | None = None
        self._last_saved_ui_hash: str | None = None
        self._first_frame_emitted = False
        self._audio_boost_until_frame: int = 0

        self._dis_flow = self._create_dis_flow()
        self._saver = AsyncScreenshotSaver(self.config.save_output_dir) if save_screenshots else None

    @property
    def current_hash(self) -> str | None:
        """Get current frame hash."""
        return self._state.current_hash

    @property
    def last_screenshot(self) -> Image.Image | None:
        """Get last stable screenshot."""
        return self._state.last_screenshot

    def close(self) -> None:
        """Close any background workers."""
        if self._saver is not None:
            self._saver.close()
            self._saver = None

    def reset(self) -> None:
        """Reset detector state."""
        self._state = ReelState()
        self._ring_buffer.clear()
        self._idle_motion_history.clear()
        self._saved_reel_count = 0
        self._last_saved_phash = None
        self._last_saved_ui_hash = None
        self._first_frame_emitted = False
        self._audio_boost_until_frame = 0

    def _ms_to_frames(self, milliseconds: int) -> int:
        fps = max(self.config.expected_fps, 1.0)
        return max(1, int(round((milliseconds / 1000.0) * fps)))

    def _create_dis_flow(self):
        preset = getattr(cv2, "DISOPTICAL_FLOW_PRESET_FAST", None)
        try:
            if preset is None:
                return None
            if hasattr(cv2, "DISOpticalFlow_create"):
                return cv2.DISOpticalFlow_create(preset)
            if hasattr(cv2, "DISOpticalFlow") and hasattr(cv2.DISOpticalFlow, "create"):
                return cv2.DISOpticalFlow.create(preset)
        except Exception:  # pragma: no cover - guarded fallback
            return None
        return None

    def _to_bgr(self, frame: Image.Image) -> np.ndarray:
        rgb = np.array(frame.convert("RGB"), dtype=np.uint8)
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)

    def _analysis_roi_gray(self, frame_bgr: np.ndarray) -> np.ndarray:
        resized = cv2.resize(
            frame_bgr,
            (self.config.analysis_width, self.config.analysis_height),
            interpolation=cv2.INTER_AREA,
        )

        h, w = resized.shape[:2]
        x1 = int(w * self.config.roi_x1)
        y1 = int(h * self.config.roi_y1)
        x2 = int(w * self.config.roi_x2)
        y2 = int(h * self.config.roi_y2)

        x1 = max(0, min(x1, w - 1))
        y1 = max(0, min(y1, h - 1))
        x2 = max(x1 + 1, min(x2, w))
        y2 = max(y1 + 1, min(y2, h))

        roi = resized[y1:y2, x1:x2]
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        return cv2.GaussianBlur(gray, (5, 5), 0)

    def _compute_flow(self, prev_gray: np.ndarray, curr_gray: np.ndarray) -> np.ndarray:
        if self._dis_flow is not None:
            return self._dis_flow.calc(prev_gray, curr_gray, None)

        return cv2.calcOpticalFlowFarneback(
            prev_gray,
            curr_gray,
            None,
            0.5,
            3,
            15,
            3,
            5,
            1.2,
            0,
        )

    def _extract_features(self, curr_roi_gray: np.ndarray) -> FlowFeatures:
        prev = self._state.previous_roi_gray
        self._state.previous_roi_gray = curr_roi_gray
        if prev is None:
            return FlowFeatures()

        flow = self._compute_flow(prev, curr_roi_gray)
        vx = flow[..., 0]
        vy = flow[..., 1]
        mag = np.sqrt((vx * vx) + (vy * vy))

        mean_abs_vx = float(np.mean(np.abs(vx)))
        mean_abs_vy = float(np.mean(np.abs(vy)))
        vertical_ratio = mean_abs_vy / (mean_abs_vx + 1e-6)
        coverage_mask = mag > self.config.motion_mag_thresh
        coverage = float(np.mean(coverage_mask))

        median_vy = 0.0
        direction_consistency = 0.0
        if np.any(coverage_mask):
            moving_vy = vy[coverage_mask]
            median_vy = float(np.median(moving_vy))
            if abs(median_vy) > 1e-6:
                direction_consistency = float(
                    np.mean(np.sign(moving_vy) == np.sign(median_vy))
                )

        mean_mag = float(np.mean(mag))

        return FlowFeatures(
            mean_abs_vx=mean_abs_vx,
            mean_abs_vy=mean_abs_vy,
            vertical_ratio=vertical_ratio,
            coverage=coverage,
            median_vy=median_vy,
            direction_consistency=direction_consistency,
            mean_mag=mean_mag,
        )

    def _is_swipe_candidate(self, features: FlowFeatures) -> bool:
        return (
            features.mean_abs_vy >= self.config.trigger_mean_vy
            and features.vertical_ratio >= self.config.trigger_vertical_ratio
            and features.coverage >= self.config.trigger_coverage
            and features.direction_consistency >= self.config.trigger_consistency
        )

    def _is_weak_swipe_candidate(self, features: FlowFeatures) -> bool:
        return (
            features.mean_abs_vy >= (self.config.trigger_mean_vy * 0.65)
            and features.vertical_ratio >= (self.config.trigger_vertical_ratio * 0.70)
            and features.coverage >= (self.config.trigger_coverage * 0.70)
        )

    def _is_impulse_swipe_candidate(self, features: FlowFeatures) -> bool:
        return (
            features.mean_abs_vy >= self.config.impulse_trigger_mean_vy
            and features.vertical_ratio >= self.config.impulse_trigger_vertical_ratio
            and features.coverage >= self.config.impulse_trigger_coverage
            and features.direction_consistency >= self.config.impulse_trigger_consistency
        )

    def _effective_settle_threshold(self) -> float:
        if not self.config.auto_calibrate_settle:
            return self.config.settle_mean_mag
        if len(self._idle_motion_history) < 20:
            return self.config.settle_mean_mag
        baseline = float(np.percentile(np.array(self._idle_motion_history), 40))
        return max(
            self.config.settle_mean_mag,
            baseline * self.config.settle_multiplier,
        )

    def _is_settled_frame(self, features: FlowFeatures) -> bool:
        return features.mean_mag <= self._effective_settle_threshold()

    def _compute_frame_phash(self, frame_bgr: np.ndarray) -> str:
        # Prefer OpenCV img_hash if available, fall back to imagehash.
        img_hash = getattr(cv2, "img_hash", None)
        if img_hash is not None and hasattr(img_hash, "PHash_create"):
            try:
                phasher = img_hash.PHash_create()
                value = phasher.compute(frame_bgr)
                return f"cv2:{value.tobytes().hex()}"
            except Exception:
                pass

        pil = Image.fromarray(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB))
        return f"ih:{str(compute_phash(pil, hash_size=8))}"

    def _extract_confirmation_regions(self, frame_bgr: np.ndarray) -> np.ndarray:
        """Build a composite image from UI regions that identify a reel."""
        h, w = frame_bgr.shape[:2]

        def crop(x1: float, y1: float, x2: float, y2: float) -> np.ndarray:
            px1 = max(0, min(int(w * x1), w - 1))
            py1 = max(0, min(int(h * y1), h - 1))
            px2 = max(px1 + 1, min(int(w * x2), w))
            py2 = max(py1 + 1, min(int(h * y2), h))
            return frame_bgr[py1:py2, px1:px2]

        right = crop(
            self.config.ui_right_x1,
            self.config.ui_right_y1,
            self.config.ui_right_x2,
            self.config.ui_right_y2,
        )
        bottom = crop(
            self.config.ui_bottom_x1,
            self.config.ui_bottom_y1,
            self.config.ui_bottom_x2,
            self.config.ui_bottom_y2,
        )

        right_resized = cv2.resize(right, (128, 416), interpolation=cv2.INTER_AREA)
        bottom_resized = cv2.resize(bottom, (384, 128), interpolation=cv2.INTER_AREA)
        canvas = np.full((544, 384, 3), 255, dtype=np.uint8)
        canvas[:416, :128] = right_resized
        canvas[416:, :] = bottom_resized
        return canvas

    def _compute_confirmation_hash(self, frame_bgr: np.ndarray) -> str:
        """Hash only the reel-identifying UI regions."""
        return self._compute_frame_phash(self._extract_confirmation_regions(frame_bgr))

    def _phash_distance(self, h1: str | None, h2: str | None) -> int:
        if h1 is None or h2 is None:
            return 10_000

        if h1.startswith("cv2:") and h2.startswith("cv2:"):
            b1 = bytes.fromhex(h1.split(":", 1)[1])
            b2 = bytes.fromhex(h2.split(":", 1)[1])
            a1 = np.frombuffer(b1, dtype=np.uint8).reshape(1, -1)
            a2 = np.frombuffer(b2, dtype=np.uint8).reshape(1, -1)
            return int(cv2.norm(a1, a2, cv2.NORM_HAMMING))

        # imagehash fallback format.
        try:
            from imagehash import hex_to_hash

            x1 = h1.split(":", 1)[1]
            x2 = h2.split(":", 1)[1]
            return int(hex_to_hash(x1) - hex_to_hash(x2))
        except Exception:
            return 10_000

    def _buffer_frame(self, frame_bgr: np.ndarray, features: FlowFeatures, timestamp_ms: float) -> None:
        analysis_gray = cv2.cvtColor(
            cv2.resize(
                frame_bgr,
                (self.config.analysis_width, self.config.analysis_height),
                interpolation=cv2.INTER_AREA,
            ),
            cv2.COLOR_BGR2GRAY,
        )

        lap_var = float(cv2.Laplacian(analysis_gray, cv2.CV_64F).var())
        brightness = float(np.mean(analysis_gray))

        self._ring_buffer.append(
            BufferedFrame(
                timestamp_ms=timestamp_ms,
                frame_bgr=frame_bgr.copy(),
                mean_mag=features.mean_mag,
                laplacian_var=lap_var,
                brightness=brightness,
            )
        )

    def _select_best_frame(self) -> BufferedFrame | None:
        if not self._ring_buffer:
            return None

        recent = list(self._ring_buffer)[-self.config.best_frame_lookback :]
        if not recent:
            return self._ring_buffer[-1]

        acceptable = [
            frame
            for frame in recent
            if frame.laplacian_var >= self.config.blur_laplacian_min
            and self.config.brightness_min <= frame.brightness <= self.config.brightness_max
        ]

        candidates = acceptable if acceptable else recent

        def score(frame: BufferedFrame) -> tuple[float, float]:
            motion_score = 1.0 / (1.0 + max(frame.mean_mag, 0.0))
            sharp_score = min(
                frame.laplacian_var / max(self.config.blur_laplacian_min * 3.0, 1.0),
                1.0,
            )
            brightness_mid = (self.config.brightness_min + self.config.brightness_max) / 2.0
            brightness_half_span = max((self.config.brightness_max - self.config.brightness_min) / 2.0, 1.0)
            brightness_score = max(
                0.0,
                1.0 - (abs(frame.brightness - brightness_mid) / brightness_half_span),
            )
            total = (0.5 * motion_score) + (0.3 * sharp_score) + (0.2 * brightness_score)
            return total, frame.timestamp_ms

        return max(candidates, key=score)

    def _enter_cooldown(self, frame_index: int) -> None:
        self._state.mode = DetectorMode.COOLDOWN
        self._state.cooldown_until_frame = frame_index + self._ms_to_frames(self.config.cooldown_ms)
        self._state.trigger_streak = 0
        self._state.weak_trigger_streak = 0
        self._state.settle_streak = 0
        self._state.is_in_transition = False
        self._state.transition_cumulative_vy = 0.0
        self._state.armed_for_transition = False

    def _emit_save(self, frame_bgr: np.ndarray) -> Path | None:
        if self._saver is None or not self.config.save_png:
            return None

        self._saved_reel_count += 1
        path = self.config.save_output_dir / f"reel_{self._saved_reel_count:04d}.png"
        self._saver.submit(path=path, frame_bgr=frame_bgr)
        return path

    def _confirm_new_reel(self, frame_index: int) -> ReelChangeType:
        min_gap_frames = self._ms_to_frames(self.config.min_confirmed_gap_ms)
        if (
            self._state.last_confirmed_frame > 0
            and (frame_index - self._state.last_confirmed_frame) < min_gap_frames
        ):
            logger.info(
                "reel_rejected reason=confirmed_gap gap_frames=%d min_gap_frames=%d",
                frame_index - self._state.last_confirmed_frame,
                min_gap_frames,
            )
            self._enter_cooldown(frame_index)
            return ReelChangeType.NONE

        best = self._select_best_frame()
        if best is None:
            logger.info("reel_rejected reason=no_buffered_frame")
            self._enter_cooldown(frame_index)
            return ReelChangeType.NONE

        candidate_hash = self._compute_frame_phash(best.frame_bgr)
        hash_distance = self._phash_distance(candidate_hash, self._last_saved_phash)
        candidate_ui_hash = self._compute_confirmation_hash(best.frame_bgr)
        ui_hash_distance = self._phash_distance(candidate_ui_hash, self._last_saved_ui_hash)

        if self._last_saved_phash is not None and hash_distance < self.config.phash_hamming_min_new_reel:
            logger.info(
                "reel_rejected reason=phash_duplicate distance=%d threshold=%d",
                hash_distance,
                self.config.phash_hamming_min_new_reel,
            )
            self._enter_cooldown(frame_index)
            return ReelChangeType.NONE

        displacement = abs(self._state.transition_cumulative_vy)
        if (
            self._last_saved_ui_hash is not None
            and ui_hash_distance < self.config.ui_phash_hamming_min_new_reel
            and displacement < (self.config.min_transition_displacement_px * 1.8)
        ):
            logger.info(
                "reel_rejected reason=ui_duplicate ui_distance=%d ui_threshold=%d displacement=%.2f",
                ui_hash_distance,
                self.config.ui_phash_hamming_min_new_reel,
                displacement,
            )
            self._enter_cooldown(frame_index)
            return ReelChangeType.NONE

        self._state.previous_hash = self._state.current_hash
        self._state.current_hash = candidate_hash
        self._last_saved_phash = candidate_hash
        self._last_saved_ui_hash = candidate_ui_hash
        self._state.last_confirmed_frame = frame_index

        screenshot_rgb = cv2.cvtColor(best.frame_bgr, cv2.COLOR_BGR2RGB)
        screenshot = Image.fromarray(screenshot_rgb)
        self._state.last_screenshot = screenshot
        self._state.pending_screenshot = screenshot

        save_path = self._emit_save(best.frame_bgr)

        logger.info(
            "reel_confirmed frame=%d phash_distance=%d saved_path=%s",
            frame_index,
            hash_distance,
            save_path,
        )

        self._enter_cooldown(frame_index)
        return ReelChangeType.NEW_REEL

    def _log_features(self, features: FlowFeatures) -> None:
        if self.config.metric_log_interval_frames <= 0:
            return
        if (self._state.frame_index % self.config.metric_log_interval_frames) != 0:
            return

        logger.debug(
            (
                "reel_features state=%s mean_abs_vx=%.3f mean_abs_vy=%.3f "
                "vertical_ratio=%.3f coverage=%.3f direction_consistency=%.3f mean_mag=%.3f "
                "settle_threshold=%.3f"
            ),
            self._state.mode.value,
            features.mean_abs_vx,
            features.mean_abs_vy,
            features.vertical_ratio,
            features.coverage,
            features.direction_consistency,
            features.mean_mag,
            self._effective_settle_threshold(),
        )

    def notify_audio_switch(self, boost_ms: int = 650) -> None:
        """Optionally boost transition confidence after an audio cut/switch event."""
        self._audio_boost_until_frame = self._state.frame_index + self._ms_to_frames(max(0, boost_ms))

    def _bootstrap_first_reel(self, frame_bgr: np.ndarray, frame_index: int) -> ReelChangeType:
        first_hash = self._compute_frame_phash(frame_bgr)
        self._state.current_hash = first_hash
        self._last_saved_phash = first_hash
        self._last_saved_ui_hash = self._compute_confirmation_hash(frame_bgr)
        self._state.last_confirmed_frame = frame_index

        screenshot_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        screenshot = Image.fromarray(screenshot_rgb)
        self._state.last_screenshot = screenshot
        self._state.pending_screenshot = screenshot
        self._state.consecutive_same_frames = 1
        self._first_frame_emitted = True

        save_path = self._emit_save(frame_bgr)
        logger.info("reel_confirmed_first_frame frame=%d saved_path=%s", frame_index, save_path)

        self._enter_cooldown(frame_index)
        return ReelChangeType.NEW_REEL

    def process_frame(self, frame: Image.Image) -> ReelChangeType:
        """Process a new frame and detect reel changes."""
        self._state.frame_index += 1
        frame_index = self._state.frame_index

        frame_bgr = self._to_bgr(frame)
        roi_gray = self._analysis_roi_gray(frame_bgr)
        features = self._extract_features(roi_gray)
        self._state.last_features = features
        timestamp_ms = (frame_index * 1000.0) / max(self.config.expected_fps, 1.0)
        self._buffer_frame(frame_bgr, features, timestamp_ms)
        self._log_features(features)

        # Calibrate expected in-reel motion floor from non-transition frames.
        if (
            self._state.mode in (DetectorMode.IDLE, DetectorMode.COOLDOWN)
            and not self._is_swipe_candidate(features)
            and features.mean_mag > 0.0
        ):
            self._idle_motion_history.append(features.mean_mag)
            if self._state.motion_floor_ema <= 0.0:
                self._state.motion_floor_ema = features.mean_mag
            else:
                alpha = 0.03
                self._state.motion_floor_ema = (
                    (1.0 - alpha) * self._state.motion_floor_ema
                ) + (alpha * features.mean_mag)

        if self._is_settled_frame(features):
            self._state.consecutive_same_frames += 1
        else:
            self._state.consecutive_same_frames = 0

        if not self._first_frame_emitted:
            return self._bootstrap_first_reel(frame_bgr, frame_index)

        if self._state.mode == DetectorMode.COOLDOWN:
            if frame_index >= self._state.cooldown_until_frame:
                self._state.mode = DetectorMode.IDLE
            else:
                return ReelChangeType.NONE

        if self._state.mode == DetectorMode.IDLE:
            if (
                not self._state.armed_for_transition
                and self._state.consecutive_same_frames >= self.config.rearm_settle_frames
            ):
                self._state.armed_for_transition = True

            if not self._state.armed_for_transition:
                return ReelChangeType.NONE

            audio_boost_active = frame_index <= self._audio_boost_until_frame
            impulse_swipe_candidate = self._is_impulse_swipe_candidate(features)
            boosted_swipe_candidate = (
                audio_boost_active
                and features.mean_abs_vy >= (self.config.trigger_mean_vy * 0.70)
                and features.vertical_ratio >= (self.config.trigger_vertical_ratio * 0.70)
                and features.coverage >= (self.config.trigger_coverage * 0.70)
            )
            weak_swipe_candidate = self._is_weak_swipe_candidate(features)

            if self._is_swipe_candidate(features) or boosted_swipe_candidate:
                self._state.trigger_streak += 1
            else:
                self._state.trigger_streak = 0

            if weak_swipe_candidate:
                self._state.weak_trigger_streak += 1
            else:
                self._state.weak_trigger_streak = 0

            if impulse_swipe_candidate or (
                self._state.trigger_streak >= self.config.trigger_consecutive_frames
                or self._state.weak_trigger_streak >= self.config.weak_trigger_consecutive_frames
            ):
                self._state.mode = DetectorMode.TRANSITION
                self._state.is_in_transition = True
                self._state.transition_started_at_frame = frame_index
                self._state.settle_streak = 0
                self._state.weak_trigger_streak = 0
                self._state.transition_cumulative_vy = 0.0
                reason = "impulse" if impulse_swipe_candidate else "streak"
                logger.info("transition_start frame=%d reason=%s", frame_index, reason)
                return ReelChangeType.TRANSITION

            return ReelChangeType.NONE

        if self._state.mode == DetectorMode.TRANSITION:
            elapsed_frames = frame_index - self._state.transition_started_at_frame
            min_transition_frames = self._ms_to_frames(self.config.min_transition_ms)
            max_transition_frames = self._ms_to_frames(self.config.max_transition_ms)
            self._state.transition_cumulative_vy += features.median_vy

            if elapsed_frames > max_transition_frames:
                # Recovery path: if motion is already near settled, move to settling
                # instead of dropping the transition outright.
                if features.mean_mag <= (self._effective_settle_threshold() * 1.15):
                    self._state.mode = DetectorMode.SETTLING
                    self._state.is_in_transition = False
                    self._state.settle_streak = 1
                    return ReelChangeType.TRANSITION

                logger.info(
                    "transition_reset reason=timeout elapsed_frames=%d max_frames=%d",
                    elapsed_frames,
                    max_transition_frames,
                )
                self._state.mode = DetectorMode.IDLE
                self._state.is_in_transition = False
                self._state.trigger_streak = 0
                self._state.weak_trigger_streak = 0
                self._state.settle_streak = 0
                self._state.transition_cumulative_vy = 0.0
                return ReelChangeType.NONE

            if elapsed_frames >= min_transition_frames and self._is_settled_frame(features):
                self._state.mode = DetectorMode.SETTLING
                self._state.is_in_transition = False
                self._state.settle_streak = 1
                return ReelChangeType.TRANSITION

            return ReelChangeType.TRANSITION

        if self._state.mode == DetectorMode.SETTLING:
            required_settle_frames = self.config.settle_consecutive_frames
            if frame_index <= self._audio_boost_until_frame:
                required_settle_frames = max(3, required_settle_frames - 2)

            if self._is_settled_frame(features):
                self._state.settle_streak += 1
            else:
                # If strong vertical motion returns, transition resumed.
                if self._is_swipe_candidate(features):
                    self._state.mode = DetectorMode.TRANSITION
                    self._state.is_in_transition = True
                    self._state.transition_started_at_frame = frame_index
                    self._state.settle_streak = 0
                    logger.info("transition_resume frame=%d", frame_index)
                    return ReelChangeType.TRANSITION
                self._state.settle_streak = max(0, self._state.settle_streak - 1)
                return ReelChangeType.NONE

            if self._state.settle_streak >= required_settle_frames:
                displacement = abs(self._state.transition_cumulative_vy)
                if displacement < self.config.min_transition_displacement_px:
                    logger.info(
                        "reel_rejected reason=low_displacement displacement=%.2f min=%.2f",
                        displacement,
                        self.config.min_transition_displacement_px,
                    )
                    self._state.mode = DetectorMode.IDLE
                    self._state.trigger_streak = 0
                    self._state.weak_trigger_streak = 0
                    self._state.settle_streak = 0
                    self._state.transition_cumulative_vy = 0.0
                    return ReelChangeType.NONE

                logger.info(
                    "settle_achieved frame=%d displacement=%.2f",
                    frame_index,
                    displacement,
                )
                return self._confirm_new_reel(frame_index)

            return ReelChangeType.NONE

        # Defensive fallback.
        self._state.mode = DetectorMode.IDLE
        self._state.is_in_transition = False
        return ReelChangeType.NONE

    def is_stable(self) -> bool:
        """Check if current content appears stable (not scrolling)."""
        return self._state.consecutive_same_frames >= self.stable_frames

    def get_stable_screenshot(self) -> Image.Image | None:
        """Get screenshot of stable content."""
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
        """Process frame and return change type and current reel number."""
        if not self.is_active:
            return ReelChangeType.NONE, 0

        change_type = self.detector.process_frame(frame)

        if change_type == ReelChangeType.NEW_REEL:
            self.reel_count += 1

        return change_type, self.reel_count
