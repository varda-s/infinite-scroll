"""Regression tests for reel detection on bundled test session videos."""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import pytest
from PIL import Image

from src.detection.reel_detector import ReelChangeType, ReelDetector


TESTSESSIONS_ROOT = Path("/Users/dschool/Desktop/infinite-scroll/tests/testsessions")


def _iter_testsession_cases() -> list[tuple[str, Path, Path, int]]:
    cases: list[tuple[str, Path, Path, int]] = []
    for case_dir in sorted(TESTSESSIONS_ROOT.iterdir()):
        if not case_dir.is_dir():
            continue
        video_path = next(case_dir.glob("*.mp4"))
        meta_path = next(case_dir.glob("*.json"))
        metadata = json.loads(meta_path.read_text())
        cases.append((case_dir.name, video_path, meta_path, int(metadata["total_reels"])))
    return cases


def _detect_reel_count(video_path: Path) -> int:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        pytest.fail(f"Unable to open video fixture: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    detector = ReelDetector(hash_threshold=15, transition_frames=2, stable_frames=2)
    detector.config.expected_fps = fps

    reel_count = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            if detector.process_frame(image) == ReelChangeType.NEW_REEL:
                reel_count += 1
    finally:
        cap.release()

    return reel_count


@pytest.mark.integration
@pytest.mark.parametrize(
    ("case_name", "video_path", "meta_path", "expected_reels"),
    _iter_testsession_cases(),
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_reel_detection_matches_bundled_testsessions(
    case_name: str,
    video_path: Path,
    meta_path: Path,
    expected_reels: int,
) -> None:
    """Bundled session videos should produce the expected reel counts."""
    detected_reels = _detect_reel_count(video_path)
    assert detected_reels == expected_reels, (
        f"{case_name} expected {expected_reels} reels per {meta_path.name}, "
        f"but detector found {detected_reels}"
    )
