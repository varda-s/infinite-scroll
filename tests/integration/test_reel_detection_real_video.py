"""Integration test using a real Instagram Reels screen recording."""

from pathlib import Path

import cv2
import pytest
from PIL import Image

from src.detection.reel_detector import ReelChangeType, ReelDetector


REAL_VIDEO_PATH = Path(
    "/Users/amanagarwal/Downloads/ScreenRecording_02-09-2026 14-17-34_1.MP4"
)
REAL_VIDEO_PATH_2 = Path(
    "/Users/amanagarwal/Downloads/ScreenRecording_02-09-2026 14-43-22_1.MP4"
)
REAL_VIDEO_PATH_3 = Path(
    "/Users/amanagarwal/Downloads/ScreenRecording_02-09-2026 16-45-45_1.MP4"
)
REAL_VIDEO_PATH_4 = Path(
    "/Users/amanagarwal/Downloads/ScreenRecording_02-09-2026 16-44-26_1.MP4"
)
REAL_VIDEO_PATH_5 = Path(
    "/Users/amanagarwal/Downloads/ScreenRecording_02-09-2026 16-58-48_1.MP4"
)


def _count_unique_reel_transitions(video_path: Path) -> tuple[int, int]:
    """Return (frame_count, reel_changes) for a real recording.

    Uses a single detector setup across all fixtures to match app behavior.
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        pytest.skip(f"Unable to open video: {video_path}")

    detector = ReelDetector(hash_threshold=12, transition_frames=2, stable_frames=2)
    new_reel_frames: list[int] = []
    frame_count = 0
    fps = cap.get(cv2.CAP_PROP_FPS) or 60.0

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break

            frame_count += 1
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            image = Image.fromarray(rgb)
            change = detector.process_frame(image)

            if change == ReelChangeType.NEW_REEL:
                new_reel_frames.append(frame_count)
    finally:
        cap.release()

    return frame_count, len(new_reel_frames)


@pytest.mark.integration
def test_reel_changes_detected_on_real_instagram_recording() -> None:
    """Run ReelDetector on the provided recording and verify changes are found."""
    if not REAL_VIDEO_PATH.exists():
        pytest.skip(f"Real video not found: {REAL_VIDEO_PATH}")

    frame_count, reel_count = _count_unique_reel_transitions(REAL_VIDEO_PATH)

    # Sanity check: we should process many frames from the recording.
    assert frame_count > 300

    # This fixture video contains 6 reels.
    assert reel_count == 6


@pytest.mark.integration
def test_reel_changes_detected_on_real_instagram_recording_2() -> None:
    """Run ReelDetector on the second provided recording and verify reel count."""
    if not REAL_VIDEO_PATH_2.exists():
        pytest.skip(f"Real video not found: {REAL_VIDEO_PATH_2}")

    frame_count, reel_count = _count_unique_reel_transitions(REAL_VIDEO_PATH_2)

    assert frame_count > 300
    # This fixture video contains 15 reels.
    assert reel_count == 15


@pytest.mark.integration
def test_reel_changes_detected_on_real_instagram_recording_3() -> None:
    """Run ReelDetector on third recording and verify reel count."""
    if not REAL_VIDEO_PATH_3.exists():
        pytest.skip(f"Real video not found: {REAL_VIDEO_PATH_3}")

    frame_count, reel_count = _count_unique_reel_transitions(REAL_VIDEO_PATH_3)

    assert frame_count > 300
    # This fixture video contains 8 reels.
    assert reel_count == 8


@pytest.mark.integration
def test_reel_changes_detected_on_real_instagram_recording_4() -> None:
    """Run ReelDetector on fourth recording and verify reel count."""
    if not REAL_VIDEO_PATH_4.exists():
        pytest.skip(f"Real video not found: {REAL_VIDEO_PATH_4}")

    frame_count, reel_count = _count_unique_reel_transitions(REAL_VIDEO_PATH_4)

    assert frame_count > 300
    # This fixture video contains 10 reels.
    assert reel_count == 10


@pytest.mark.integration
def test_reel_changes_detected_on_real_instagram_recording_5() -> None:
    """Run ReelDetector on fifth recording and verify reel count."""
    if not REAL_VIDEO_PATH_5.exists():
        pytest.skip(f"Real video not found: {REAL_VIDEO_PATH_5}")

    frame_count, reel_count = _count_unique_reel_transitions(REAL_VIDEO_PATH_5)

    assert frame_count > 300
    # This fixture video contains 12 reels.
    assert reel_count == 12
