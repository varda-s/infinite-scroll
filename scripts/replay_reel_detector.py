#!/usr/bin/env python3
"""Replay recorded sessions through ReelDetector and compare against fixtures."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import cv2
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.detection.reel_detector import ReelChangeType, ReelDetector  # noqa: E402


VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v"}


@dataclass
class ExpectedReel:
    reel_id: int
    start_s: float
    duration_s: float
    label: str


@dataclass
class SessionFixture:
    name: str
    video_path: Path
    metadata_path: Path
    total_duration_s: float
    total_reels: int
    reels: list[ExpectedReel]


def _parse_start(value: object) -> float:
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()
    if re.fullmatch(r"\d{1,2}\.\d{2}", text):
        minutes, seconds = text.split(".")
        return int(minutes) * 60 + int(seconds)

    return float(text)


def _load_fixture_json(path: Path) -> dict:
    # Some fixture files include a trailing comma before the closing bracket.
    raw = path.read_text(encoding="utf-8")
    raw = re.sub(r",\s*([}\]])", r"\1", raw)
    return json.loads(raw)


def load_fixture(session_dir: Path) -> SessionFixture:
    metadata_path = next(session_dir.glob("*.json"))
    video_path = next(p for p in session_dir.iterdir() if p.suffix.lower() in VIDEO_SUFFIXES)
    payload = _load_fixture_json(metadata_path)

    reels = [
        ExpectedReel(
            reel_id=int(item["reel_id"]),
            start_s=_parse_start(item["start"]),
            duration_s=float(item["duration"]),
            label=str(item.get("label", "")),
        )
        for item in payload["reels"]
    ]

    return SessionFixture(
        name=str(payload.get("name", session_dir.name)),
        video_path=video_path,
        metadata_path=metadata_path,
        total_duration_s=float(payload["total_duration"]),
        total_reels=int(payload["total_reels"]),
        reels=reels,
    )


def _format_seconds(value: float) -> str:
    return f"{value:7.2f}s"


def replay_fixture(
    fixture: SessionFixture,
    hash_threshold: int,
    transition_frames: int,
    stable_frames: int,
) -> dict:
    cap = cv2.VideoCapture(str(fixture.video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Unable to open video: {fixture.video_path}")

    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    video_duration = (frame_count / fps) if fps > 0 else fixture.total_duration_s

    detector = ReelDetector(
        hash_threshold=hash_threshold,
        transition_frames=transition_frames,
        stable_frames=stable_frames,
    )

    detected_start_s: list[float] = []
    processed_frames = 0

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            processed_frames += 1
            image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            change = detector.process_frame(image)
            if change == ReelChangeType.NEW_REEL and fps > 0:
                detected_start_s.append((processed_frames - 1) / fps)
    finally:
        cap.release()

    expected_start_s = [reel.start_s for reel in fixture.reels]
    expected_duration_s = [reel.duration_s for reel in fixture.reels]

    detected_duration_s: list[float] = []
    for idx, start in enumerate(detected_start_s):
        next_start = detected_start_s[idx + 1] if idx + 1 < len(detected_start_s) else video_duration
        detected_duration_s.append(max(0.0, next_start - start))

    compared = min(len(expected_start_s), len(detected_start_s))
    boundary_errors = [
        detected_start_s[i] - expected_start_s[i]
        for i in range(compared)
    ]
    duration_errors = [
        detected_duration_s[i] - expected_duration_s[i]
        for i in range(min(len(expected_duration_s), len(detected_duration_s)))
    ]

    return {
        "fixture": fixture,
        "fps": fps,
        "frame_count": frame_count,
        "video_duration_s": video_duration,
        "processed_frames": processed_frames,
        "expected_start_s": expected_start_s,
        "expected_duration_s": expected_duration_s,
        "detected_start_s": detected_start_s,
        "detected_duration_s": detected_duration_s,
        "boundary_errors": boundary_errors,
        "duration_errors": duration_errors,
    }


def print_report(result: dict) -> None:
    fixture: SessionFixture = result["fixture"]
    expected = result["expected_start_s"]
    detected = result["detected_start_s"]
    boundary_errors = result["boundary_errors"]
    duration_errors = result["duration_errors"]

    print(f"\n== {fixture.name} ==")
    print(f"video: {fixture.video_path}")
    print(
        "fps={fps:.3f} frames={frames} video_duration={video:.2f}s fixture_duration={fixture_dur:.2f}s".format(
            fps=result["fps"],
            frames=result["frame_count"],
            video=result["video_duration_s"],
            fixture_dur=fixture.total_duration_s,
        )
    )
    print(
        "expected_reels={exp_meta}/{exp_count} detected_reels={det}".format(
            exp_meta=fixture.total_reels,
            exp_count=len(fixture.reels),
            det=len(detected),
        )
    )

    if fixture.total_reels != len(fixture.reels):
        print(
            f"metadata mismatch: total_reels says {fixture.total_reels}, "
            f"but reels list has {len(fixture.reels)}"
        )

    if boundary_errors:
        avg_boundary = sum(abs(x) for x in boundary_errors) / len(boundary_errors)
        worst_boundary = max(abs(x) for x in boundary_errors)
        print(
            f"boundary drift: avg={avg_boundary:.2f}s worst={worst_boundary:.2f}s "
            f"across {len(boundary_errors)} matched reels"
        )
    else:
        print("boundary drift: no matched reels")

    if duration_errors:
        avg_duration = sum(abs(x) for x in duration_errors) / len(duration_errors)
        worst_duration = max(abs(x) for x in duration_errors)
        print(
            f"duration drift: avg={avg_duration:.2f}s worst={worst_duration:.2f}s "
            f"across {len(duration_errors)} matched reels"
        )
    else:
        print("duration drift: no matched reels")

    compared = min(len(expected), len(detected), 8)
    if compared:
        print("first matched boundaries:")
        for idx in range(compared):
            label = fixture.reels[idx].label
            print(
                f"  reel {idx + 1:02d} "
                f"expected={_format_seconds(expected[idx])} "
                f"detected={_format_seconds(detected[idx])} "
                f"delta={boundary_errors[idx]:+6.2f}s "
                f"label={label}"
            )

    extras = len(detected) - len(expected)
    if extras > 0:
        print(f"extra detections: {extras}")
    elif extras < 0:
        print(f"missed detections: {-extras}")


def iter_session_dirs(root: Path) -> list[Path]:
    return sorted(path for path in root.iterdir() if path.is_dir())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT / "tests" / "testsessions",
        help="Root directory containing session fixture subdirectories.",
    )
    parser.add_argument("--session", action="append", help="Specific session folder name(s) to replay.")
    parser.add_argument("--hash-threshold", type=int, default=15)
    parser.add_argument("--transition-frames", type=int, default=3)
    parser.add_argument("--stable-frames", type=int, default=2)
    args = parser.parse_args()

    root = args.root.resolve()
    if not root.exists():
        raise SystemExit(f"Fixture root not found: {root}")

    session_dirs = iter_session_dirs(root)
    if args.session:
        wanted = set(args.session)
        session_dirs = [path for path in session_dirs if path.name in wanted]

    if not session_dirs:
        raise SystemExit("No session fixtures selected.")

    all_results = []
    for session_dir in session_dirs:
        fixture = load_fixture(session_dir)
        result = replay_fixture(
            fixture,
            hash_threshold=args.hash_threshold,
            transition_frames=args.transition_frames,
            stable_frames=args.stable_frames,
        )
        all_results.append(result)
        print_report(result)

    matched_boundaries = [
        abs(err)
        for result in all_results
        for err in result["boundary_errors"]
    ]
    matched_durations = [
        abs(err)
        for result in all_results
        for err in result["duration_errors"]
    ]
    expected_total = sum(len(result["expected_start_s"]) for result in all_results)
    detected_total = sum(len(result["detected_start_s"]) for result in all_results)

    print("\n== aggregate ==")
    print(f"sessions={len(all_results)} expected_reels={expected_total} detected_reels={detected_total}")
    if matched_boundaries:
        print(
            "boundary drift: avg={avg:.2f}s worst={worst:.2f}s".format(
                avg=sum(matched_boundaries) / len(matched_boundaries),
                worst=max(matched_boundaries),
            )
        )
    if matched_durations:
        print(
            "duration drift: avg={avg:.2f}s worst={worst:.2f}s".format(
                avg=sum(matched_durations) / len(matched_durations),
                worst=max(matched_durations),
            )
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
