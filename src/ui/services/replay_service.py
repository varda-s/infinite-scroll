"""Build and serve replay videos for completed sessions."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

from src.printing.base import BasePrinter
from src.ui.database.repository import SessionRepository
from src.ui.services.media_paths import OUTPUT_ROOT


REPLAY_FPS = 20.0
REPLAY_DIR = OUTPUT_ROOT / "replays"
REPLAY_FORMAT_VERSION = 2

# Receipt/video layout
FRAME_WIDTH = 720
FRAME_HEIGHT = 1280
RECEIPT_WIDTH = 560
RECEIPT_MARGIN_X = (FRAME_WIDTH - RECEIPT_WIDTH) // 2
VIEWPORT_HEIGHT = FRAME_HEIGHT - 120
PAPER_TOP = 80
TEXT_MARGIN = 24
TEXT_WIDTH = RECEIPT_WIDTH - (TEXT_MARGIN * 2)


def get_session_replay_path(session_id: int) -> Path:
    """Return deterministic replay path for a session."""
    return REPLAY_DIR / f"session_{session_id}.mp4"


def ensure_session_replay_video(session_id: int) -> str | None:
    """Create replay video if possible and return absolute path."""
    replay_path = get_session_replay_path(session_id)
    if _is_replay_current(replay_path):
        _normalize_existing_replay_for_browser(replay_path)
        return str(replay_path.resolve())

    _delete_replay_artifacts(replay_path)

    session = SessionRepository.get_session(session_id)
    receipts = SessionRepository.get_session_receipts(session_id)
    image_receipts = [r for r in receipts if r.screenshot_path and Path(r.screenshot_path).exists()]
    if session is None or not image_receipts:
        return None

    replay_path.parent.mkdir(parents=True, exist_ok=True)
    ok = _write_replay_video(replay_path, session, image_receipts)
    if not ok:
        return None

    _write_replay_meta(replay_path)
    return str(replay_path.resolve())


def _write_replay_video(replay_path: Path, session, receipts: Iterable) -> bool:
    """Write receipt-style replay that mimics live thermal printing."""
    receipts = list(receipts)
    if not receipts:
        return False

    temp_path = replay_path.with_suffix(".tmp.mp4")
    if temp_path.exists():
        try:
            temp_path.unlink()
        except Exception:
            pass

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(temp_path), fourcc, REPLAY_FPS, (FRAME_WIDTH, FRAME_HEIGHT))
    if not writer.isOpened():
        return False

    paper = Image.new("RGB", (RECEIPT_WIDTH, 1200), "white")
    printed_height = 0
    mono_font = _load_font(22)
    title_font = _load_font(28)

    try:
        # Initial header print
        header_block = _build_header_block(session, mono_font, title_font)
        paper, printed_height = _animate_print_block(
            writer=writer,
            paper=paper,
            printed_height=printed_height,
            block=header_block,
            print_seconds=0.8,
        )

        # Reel playback: watch duration first, then print receipt for completed reel
        for display_reel_number, receipt in enumerate(receipts, start=1):
            hold_seconds = max(0.2, float(receipt.duration_seconds))
            _write_hold_frames(writer, paper, printed_height, hold_seconds)

            reel_block = _build_reel_block(
                receipt,
                mono_font,
                title_font,
                display_reel_number=display_reel_number,
            )
            paper, printed_height = _animate_print_block(
                writer=writer,
                paper=paper,
                printed_height=printed_height,
                block=reel_block,
                print_seconds=0.9,
            )

        summary_block = _build_summary_block(session, mono_font, title_font)
        paper, printed_height = _animate_print_block(
            writer=writer,
            paper=paper,
            printed_height=printed_height,
            block=summary_block,
            print_seconds=1.0,
        )

        _write_hold_frames(writer, paper, printed_height, 2.0)
    finally:
        writer.release()

    if not temp_path.exists() or temp_path.stat().st_size <= 1024:
        return False

    if not _transcode_to_browser_mp4(temp_path, replay_path):
        temp_path.replace(replay_path)
    elif temp_path.exists():
        try:
            temp_path.unlink()
        except Exception:
            pass

    return replay_path.exists() and replay_path.stat().st_size > 1024


def _build_header_block(session, mono_font: ImageFont.FreeTypeFont, title_font: ImageFont.FreeTypeFont) -> Image.Image:
    lines = [
        ("INSTAGRAM REEL TRACKER", "center", title_font),
        ("=" * 32, "center", mono_font),
        (f"Session: {session.start_time.strftime('%Y-%m-%d %H:%M:%S')}", "left", mono_font),
        ("-" * 32, "center", mono_font),
        ("", "left", mono_font),
    ]
    return _render_text_block(lines)


def _build_reel_block(
    receipt,
    mono_font: ImageFont.FreeTypeFont,
    title_font: ImageFont.FreeTypeFont,
    display_reel_number: int,
) -> Image.Image:
    duration_str = BasePrinter.format_duration(float(receipt.duration_seconds))
    screenshot = _load_receipt_screenshot(receipt.screenshot_path)

    content_height = 0
    text_lines_top = [
        (f"REEL #{display_reel_number}", "center", title_font),
        ("-" * 32, "center", mono_font),
        ("", "left", mono_font),
    ]
    top_block = _render_text_block(text_lines_top)
    content_height += top_block.height

    image_block = _render_centered_image_block(screenshot)
    content_height += image_block.height

    text_lines_bottom = [
        ("", "left", mono_font),
        ("-" * 32, "center", mono_font),
        (f"Time spent: {duration_str}", "left", mono_font),
        (f"Captured: {receipt.timestamp.strftime('%H:%M:%S')}", "left", mono_font),
        ("-" * 32, "center", mono_font),
        ("", "left", mono_font),
    ]
    bottom_block = _render_text_block(text_lines_bottom)
    content_height += bottom_block.height

    block = Image.new("RGB", (RECEIPT_WIDTH, content_height), "white")
    y = 0
    block.paste(top_block, (0, y))
    y += top_block.height
    block.paste(image_block, (0, y))
    y += image_block.height
    block.paste(bottom_block, (0, y))
    return block


def _build_summary_block(session, mono_font: ImageFont.FreeTypeFont, title_font: ImageFont.FreeTypeFont) -> Image.Image:
    avg = session.total_time_seconds / session.total_reels if session.total_reels else 0.0
    lines = [
        ("", "left", mono_font),
        ("=" * 32, "center", mono_font),
        ("SESSION COMPLETE", "center", title_font),
        ("=" * 32, "center", mono_font),
        (f"Total reels: {session.total_reels}", "left", mono_font),
        (f"Total time: {BasePrinter.format_duration(session.total_time_seconds)}", "left", mono_font),
        (f"Avg per reel: {BasePrinter.format_duration(avg)}", "left", mono_font),
        ("-" * 32, "center", mono_font),
        ("THANK YOU FOR SCROLLING!", "center", mono_font),
        ("", "left", mono_font),
    ]
    return _render_text_block(lines)


def _render_text_block(lines: list[tuple[str, str, ImageFont.FreeTypeFont]]) -> Image.Image:
    probe = Image.new("RGB", (RECEIPT_WIDTH, 10), "white")
    draw = ImageDraw.Draw(probe)

    y = 16
    metrics: list[tuple[str, str, ImageFont.FreeTypeFont, int]] = []
    for text, align, font in lines:
        bbox = draw.textbbox((0, 0), text if text else " ", font=font)
        h = max(18, bbox[3] - bbox[1])
        metrics.append((text, align, font, h))
        y += h + 10

    block = Image.new("RGB", (RECEIPT_WIDTH, y + 10), "white")
    draw = ImageDraw.Draw(block)

    cursor_y = 16
    for text, align, font, h in metrics:
        if align == "center":
            bbox = draw.textbbox((0, 0), text if text else " ", font=font)
            text_w = bbox[2] - bbox[0]
            x = max(TEXT_MARGIN, (RECEIPT_WIDTH - text_w) // 2)
        else:
            x = TEXT_MARGIN
        draw.text((x, cursor_y), text, fill="black", font=font)
        cursor_y += h + 10

    return block


def _render_centered_image_block(image: Image.Image) -> Image.Image:
    target_w = TEXT_WIDTH
    max_h = 560
    fitted = ImageOps.contain(image.convert("RGB"), (target_w, max_h))
    fitted = ImageOps.grayscale(fitted).convert("RGB")

    block_h = fitted.height + 24
    block = Image.new("RGB", (RECEIPT_WIDTH, block_h), "white")
    x = (RECEIPT_WIDTH - fitted.width) // 2
    block.paste(fitted, (x, 12))
    return block


def _load_receipt_screenshot(path: str | None) -> Image.Image:
    if not path:
        return Image.new("RGB", (TEXT_WIDTH, 240), "white")
    try:
        with Image.open(path) as img:
            return img.convert("RGB")
    except Exception:
        return Image.new("RGB", (TEXT_WIDTH, 240), "white")


def _animate_print_block(
    writer: cv2.VideoWriter,
    paper: Image.Image,
    printed_height: int,
    block: Image.Image,
    print_seconds: float,
) -> tuple[Image.Image, int]:
    paper = _ensure_paper_height(paper, printed_height + block.height + 40)
    steps = max(2, int(print_seconds * REPLAY_FPS))

    for step in range(1, steps + 1):
        reveal = max(1, int(block.height * step / steps))
        preview = paper.copy()
        preview.paste(block.crop((0, 0, block.width, reveal)), (0, printed_height))
        writer.write(_compose_frame(preview, printed_height + reveal))

    paper.paste(block, (0, printed_height))
    printed_height += block.height
    return paper, printed_height


def _write_hold_frames(writer: cv2.VideoWriter, paper: Image.Image, printed_height: int, hold_seconds: float) -> None:
    count = max(1, int(hold_seconds * REPLAY_FPS))
    frame = _compose_frame(paper, printed_height)
    for _ in range(count):
        writer.write(frame)


def _ensure_paper_height(paper: Image.Image, needed_height: int) -> Image.Image:
    if paper.height >= needed_height:
        return paper
    new_height = max(needed_height, int(paper.height * 1.5))
    extended = Image.new("RGB", (paper.width, new_height), "white")
    extended.paste(paper, (0, 0))
    return extended


def _compose_frame(paper: Image.Image, printed_height: int) -> np.ndarray:
    frame = Image.new("RGB", (FRAME_WIDTH, FRAME_HEIGHT), (240, 240, 240))
    draw = ImageDraw.Draw(frame)

    # Printer slot / top bar
    draw.rounded_rectangle((40, 24, FRAME_WIDTH - 40, 68), radius=12, fill=(60, 60, 60))

    visible_start = max(0, printed_height - VIEWPORT_HEIGHT)
    visible_end = max(visible_start + 1, min(paper.height, visible_start + VIEWPORT_HEIGHT))
    crop = paper.crop((0, visible_start, RECEIPT_WIDTH, visible_end))

    # Paper shadow
    x0 = RECEIPT_MARGIN_X
    y0 = PAPER_TOP
    draw.rectangle((x0 + 6, y0 + 8, x0 + RECEIPT_WIDTH + 6, y0 + crop.height + 8), fill=(190, 190, 190))
    frame.paste(crop, (x0, y0))

    return cv2.cvtColor(np.array(frame), cv2.COLOR_RGB2BGR)


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Menlo.ttc",
        "/System/Library/Fonts/SFNSMono.ttf",
        "/System/Library/Fonts/Monaco.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except Exception:
            continue
    return ImageFont.load_default()


def _replay_meta_path(replay_path: Path) -> Path:
    return replay_path.with_suffix(".json")


def _write_replay_meta(replay_path: Path) -> None:
    meta = {"format_version": REPLAY_FORMAT_VERSION}
    try:
        _replay_meta_path(replay_path).write_text(json.dumps(meta), encoding="utf-8")
    except Exception:
        pass


def _is_replay_current(replay_path: Path) -> bool:
    if not replay_path.exists() or replay_path.stat().st_size <= 1024:
        return False

    meta_path = _replay_meta_path(replay_path)
    if not meta_path.exists():
        return False

    try:
        payload = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return False

    return payload.get("format_version") == REPLAY_FORMAT_VERSION


def _delete_replay_artifacts(replay_path: Path) -> None:
    for p in [replay_path, _replay_meta_path(replay_path), replay_path.with_suffix(".tmp.mp4")]:
        if p.exists():
            try:
                p.unlink()
            except Exception:
                pass


def _normalize_existing_replay_for_browser(replay_path: Path) -> None:
    """Transcode existing non-H.264 replays so browser playback is reliable."""
    codec = _probe_video_codec(replay_path)
    if codec in {"h264", "avc1"}:
        return

    temp_path = replay_path.with_suffix(".compat.mp4")
    if temp_path.exists():
        try:
            temp_path.unlink()
        except Exception:
            pass

    if _transcode_to_browser_mp4(replay_path, temp_path):
        try:
            temp_path.replace(replay_path)
        except Exception:
            pass


def _probe_video_codec(video_path: Path) -> str | None:
    """Return primary video codec when ffprobe is available."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    cmd = [
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=codec_name",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
    except Exception:
        return None
    if result.returncode != 0:
        return None
    codec = result.stdout.strip().lower()
    return codec or None


def _transcode_to_browser_mp4(src_path: Path, dst_path: Path) -> bool:
    """Transcode to H.264 + faststart for better browser playback compatibility."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return False

    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(src_path),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        "-an",
        str(dst_path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
    except Exception:
        return False

    if result.returncode != 0 or not dst_path.exists() or dst_path.stat().st_size <= 1024:
        return False

    return True
