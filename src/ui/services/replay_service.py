"""Build and serve replay videos for completed sessions."""

from __future__ import annotations

import json
import shutil
import subprocess
import wave
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

from src.printing.legacy_format import (
    LINE_WIDTH,
    PRINT_WIDTH_MM,
    ReelReceiptEntry,
    SIDE_MARGIN_MM,
    build_summary_lines,
    get_legacy_asset_path,
    load_legacy_image,
    parse_topics_from_receipt_content,
    placeholder_topic,
    preprocess_reel_screenshot,
)
from src.ui.database.repository import SessionRepository
from src.ui.services.media_paths import OUTPUT_ROOT


REPLAY_FPS = 20.0
REPLAY_DIR = OUTPUT_ROOT / "replays"
REPLAY_FORMAT_VERSION = 7

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
    # Smaller mono font better matches thermal-print density and prevents clipping.
    mono_font = _load_font(16)
    title_font = _load_font(24)
    parsed_topics = parse_topics_from_receipt_content(getattr(session, "receipt_content", None))
    summary_entries: list[ReelReceiptEntry] = []

    try:
        # Initial header print
        header_block = _build_header_block(mono_font, title_font)
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

            topic = parsed_topics.get(
                display_reel_number,
                parsed_topics.get(receipt.reel_number, placeholder_topic(display_reel_number)),
            )
            summary_entries.append(
                ReelReceiptEntry(
                    reel_number=display_reel_number,
                    duration_seconds=float(receipt.duration_seconds),
                    topic=topic,
                )
            )

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

        art_block = _build_legacy_asset_block(
            asset_name="art.png",
            mono_font=mono_font,
            fallback_lines=[("ART", "center", title_font)],
        )
        paper, printed_height = _animate_print_block(
            writer=writer,
            paper=paper,
            printed_height=printed_height,
            block=art_block,
            print_seconds=0.8,
        )

        summary_image_block = _build_legacy_asset_block(
            asset_name="summary.png",
            mono_font=mono_font,
            fallback_lines=[("SUMMARY", "center", title_font)],
        )
        paper, printed_height = _animate_print_block(
            writer=writer,
            paper=paper,
            printed_height=printed_height,
            block=summary_image_block,
            print_seconds=0.8,
        )

        summary_line_width = _max_chars_for_receipt_width(mono_font)
        summary_block = _build_summary_block(
            summary_entries,
            mono_font,
            title_font,
            line_width=summary_line_width,
        )
        paper, printed_height = _animate_print_block(
            writer=writer,
            paper=paper,
            printed_height=printed_height,
            block=summary_block,
            print_seconds=1.0,
        )

        footer_block = _build_legacy_asset_block(
            asset_name="footer.png",
            mono_font=mono_font,
            fallback_lines=[("FOOTER", "center", title_font)],
        )
        paper, printed_height = _animate_print_block(
            writer=writer,
            paper=paper,
            printed_height=printed_height,
            block=footer_block,
            print_seconds=0.8,
        )

        _write_hold_frames(writer, paper, printed_height, 2.0)
    finally:
        writer.release()

    if not temp_path.exists() or temp_path.stat().st_size <= 1024:
        return False

    if not _transcode_to_browser_mp4(temp_path, replay_path, add_legacy_audio=True):
        temp_path.replace(replay_path)
    elif temp_path.exists():
        try:
            temp_path.unlink()
        except Exception:
            pass

    return replay_path.exists() and replay_path.stat().st_size > 1024


def _build_header_block(mono_font: ImageFont.FreeTypeFont, title_font: ImageFont.FreeTypeFont) -> Image.Image:
    return _build_legacy_asset_block(
        asset_name="header.png",
        mono_font=mono_font,
        fallback_lines=[("REEL RECEIPT", "center", title_font)],
    )


def _build_reel_block(
    receipt,
    mono_font: ImageFont.FreeTypeFont,
    title_font: ImageFont.FreeTypeFont,
    display_reel_number: int,
) -> Image.Image:
    screenshot = _load_receipt_screenshot(receipt.screenshot_path)

    content_height = 0
    text_lines_top = [
        (f"Started: {receipt.timestamp.strftime('%Y-%m-%d %H:%M:%S')}", "center", mono_font),
    ]
    top_block = _render_text_block(
        text_lines_top,
        top_padding=6,
        line_gap=2,
        bottom_padding=2,
        min_line_height=16,
    )
    content_height += top_block.height

    image_block = _render_centered_image_block(screenshot)
    content_height += image_block.height

    text_lines_bottom = [
        (f"Time Spent: {float(receipt.duration_seconds):.2f}s", "center", mono_font),
    ]
    bottom_block = _render_text_block(
        text_lines_bottom,
        top_padding=2,
        line_gap=2,
        bottom_padding=4,
        min_line_height=16,
    )
    content_height += bottom_block.height

    block = Image.new("RGB", (RECEIPT_WIDTH, content_height), "white")
    y = 0
    block.paste(top_block, (0, y))
    y += top_block.height
    block.paste(image_block, (0, y))
    y += image_block.height
    block.paste(bottom_block, (0, y))
    return block


def _build_summary_block(
    entries: Iterable[ReelReceiptEntry],
    mono_font: ImageFont.FreeTypeFont,
    title_font: ImageFont.FreeTypeFont,
    line_width: int = LINE_WIDTH,
) -> Image.Image:
    summary_lines = build_summary_lines(entries, line_width=line_width)
    lines: list[tuple[str, str, ImageFont.FreeTypeFont]] = []

    for idx, line in enumerate(summary_lines):
        if idx == 0 and line == "REEL RECEIPT":
            lines.append((line, "center", title_font))
            continue
        if line.startswith("TOTAL"):
            lines.append((line, "left", mono_font))
            continue
        lines.append((line, "left", mono_font))

    return _render_text_block(lines)


def _build_legacy_asset_block(
    asset_name: str,
    mono_font: ImageFont.FreeTypeFont,
    fallback_lines: list[tuple[str, str, ImageFont.FreeTypeFont]],
) -> Image.Image:
    image = load_legacy_image(asset_name)
    if image is None:
        return _render_text_block(fallback_lines)
    return _render_full_width_image_block(image)


def _render_text_block(
    lines: list[tuple[str, str, ImageFont.FreeTypeFont]],
    top_padding: int = 16,
    line_gap: int = 10,
    bottom_padding: int = 10,
    min_line_height: int = 18,
) -> Image.Image:
    probe = Image.new("RGB", (RECEIPT_WIDTH, 10), "white")
    draw = ImageDraw.Draw(probe)

    y = top_padding
    metrics: list[tuple[str, str, ImageFont.FreeTypeFont, int]] = []
    for text, align, font in lines:
        bbox = draw.textbbox((0, 0), text if text else " ", font=font)
        h = max(min_line_height, bbox[3] - bbox[1])
        metrics.append((text, align, font, h))
        y += h + line_gap

    block = Image.new("RGB", (RECEIPT_WIDTH, y + bottom_padding), "white")
    draw = ImageDraw.Draw(block)

    cursor_y = top_padding
    for text, align, font, h in metrics:
        if align == "center":
            bbox = draw.textbbox((0, 0), text if text else " ", font=font)
            text_w = bbox[2] - bbox[0]
            x = max(TEXT_MARGIN, (RECEIPT_WIDTH - text_w) // 2)
        else:
            x = TEXT_MARGIN
        draw.text((x, cursor_y), text, fill="black", font=font)
        cursor_y += h + line_gap

    return block


def _render_centered_image_block(image: Image.Image) -> Image.Image:
    margin_px = max(1, int(RECEIPT_WIDTH * (SIDE_MARGIN_MM / PRINT_WIDTH_MM)))
    target_w = max(1, RECEIPT_WIDTH - (2 * margin_px))
    max_h = 980
    fitted = ImageOps.contain(image.convert("RGB"), (target_w, max_h))
    fitted = ImageOps.grayscale(fitted).convert("RGB")

    block_h = fitted.height + 6
    block = Image.new("RGB", (RECEIPT_WIDTH, block_h), "white")
    x = (RECEIPT_WIDTH - fitted.width) // 2
    block.paste(fitted, (x, 3))
    return block


def _render_full_width_image_block(image: Image.Image) -> Image.Image:
    max_h = 760
    fitted = ImageOps.contain(image.convert("RGB"), (RECEIPT_WIDTH, max_h))
    fitted = ImageOps.grayscale(fitted).convert("RGB")

    block_h = fitted.height + 16
    block = Image.new("RGB", (RECEIPT_WIDTH, block_h), "white")
    x = (RECEIPT_WIDTH - fitted.width) // 2
    block.paste(fitted, (x, 8))
    return block


def _max_chars_for_receipt_width(font: ImageFont.FreeTypeFont) -> int:
    """Estimate max monospace chars that fit in replay receipt text width."""
    probe = Image.new("RGB", (RECEIPT_WIDTH, 32), "white")
    draw = ImageDraw.Draw(probe)
    bbox = draw.textbbox((0, 0), "0", font=font)
    char_w = max(1, bbox[2] - bbox[0])
    available = max(1, TEXT_WIDTH)
    # Keep a conservative safety margin to avoid right-edge clipping in replay.
    fit = max(24, min(LINE_WIDTH - 2, int(available // char_w) - 2))
    return fit


def _load_receipt_screenshot(path: str | None) -> Image.Image:
    if not path:
        return Image.new("RGB", (TEXT_WIDTH, 240), "white")
    try:
        with Image.open(path) as img:
            return preprocess_reel_screenshot(img.convert("RGB"))
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

    if _transcode_to_browser_mp4(replay_path, temp_path, add_legacy_audio=False):
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


def _legacy_replay_audio_plan(video_duration_s: float) -> list[tuple[Path, int]]:
    """Return [(audio_path, delay_ms)] for replay audio overlays.

    Legacy UX uses only the end processing audio cue.
    """
    clips: list[tuple[Path, int]] = []
    outro = get_legacy_asset_path("waitaudio.wav")

    if outro.exists():
        outro_start_ms = 0
        outro_duration_s = _wav_duration_seconds(outro)
        if outro_duration_s > 0:
            outro_start_ms = int(max(0.0, video_duration_s - outro_duration_s) * 1000.0)
        clips.append((outro, outro_start_ms))

    return clips


def _wav_duration_seconds(path: Path) -> float:
    """Return WAV duration, or 0 if unreadable."""
    try:
        with wave.open(str(path), "rb") as wavf:
            frame_rate = wavf.getframerate()
            n_frames = wavf.getnframes()
            if frame_rate <= 0:
                return 0.0
            return float(n_frames) / float(frame_rate)
    except Exception:
        return 0.0


def _probe_video_duration_seconds(video_path: Path) -> float | None:
    """Return video duration in seconds via ffprobe/cv2."""
    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        cmd = [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                raw = result.stdout.strip()
                if raw:
                    return float(raw)
        except Exception:
            pass

    try:
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return None
        fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
        frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0
        cap.release()
        if fps > 0 and frame_count > 0:
            return float(frame_count) / float(fps)
    except Exception:
        return None

    return None


def _transcode_to_browser_mp4(src_path: Path, dst_path: Path, add_legacy_audio: bool = True) -> bool:
    """Transcode to H.264 + faststart for better browser playback compatibility."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return False

    cmd: list[str]
    if add_legacy_audio:
        video_duration = _probe_video_duration_seconds(src_path)
        audio_clips = _legacy_replay_audio_plan(video_duration or 0.0) if video_duration else []
    else:
        audio_clips = []

    if audio_clips and video_duration and video_duration > 0:
        cmd = [ffmpeg, "-y", "-i", str(src_path)]
        for clip_path, _ in audio_clips:
            cmd.extend(["-i", str(clip_path)])

        filter_parts = [f"anullsrc=r=44100:cl=stereo,atrim=0:{video_duration:.3f}[base]"]
        mix_inputs = ["[base]"]
        for i, (_, delay_ms) in enumerate(audio_clips, start=1):
            out_label = f"a{i}"
            filter_parts.append(f"[{i}:a]adelay={delay_ms}|{delay_ms}[{out_label}]")
            mix_inputs.append(f"[{out_label}]")

        mix = "".join(mix_inputs)
        filter_parts.append(
            f"{mix}amix=inputs={len(mix_inputs)}:duration=first:dropout_transition=0[aout]"
        )
        filter_complex = ";".join(filter_parts)

        cmd.extend(
            [
                "-filter_complex",
                filter_complex,
                "-map",
                "0:v:0",
                "-map",
                "[aout]",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-movflags",
                "+faststart",
                str(dst_path),
            ]
        )
    else:
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
