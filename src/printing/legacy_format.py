"""Shared helpers for the legacy `screentimecode` receipt format."""

from __future__ import annotations

import random
import re
import shutil
import subprocess
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
from PIL import Image, UnidentifiedImageError

LINE_WIDTH = 40
PRINTER_DPI = 203
PRINT_WIDTH_MM = 71
PRINT_FEED_AFTER_IMAGE = 6
SIDE_MARGIN_MM = 2.0

BUNDLED_LEGACY_ASSET_DIR = Path(__file__).resolve().parent / "assets" / "legacy"

REEL_TOPICS = [
    "Cooking Tutorial",
    "Gaming Highlights",
    "Travel Vlog",
    "Comedy Skit",
    "Workout Tips",
    "Tech Review",
    "DIY Craft",
    "Street Interview",
    "Food Review",
    "Pet Video",
]

_OLD_REEL_ITEM_PATTERN = re.compile(r"^Reel\s+(\d+)\s+\[(.*?)\]")
_NEW_REEL_ITEM_PATTERN = re.compile(r"^\[(.*?)\]\.+\$\d")
_PLAIN_REEL_ITEM_PATTERN = re.compile(r"^(.+?)\.+\$\d")


@dataclass
class ReelReceiptEntry:
    """Itemized summary row for one reel."""

    reel_number: int
    duration_seconds: float
    topic: str


def get_legacy_asset_path(filename: str) -> Path:
    """Return absolute path to a legacy receipt asset."""
    return BUNDLED_LEGACY_ASSET_DIR / filename


def load_legacy_image(filename: str) -> Image.Image | None:
    """Load an image from legacy assets if present."""
    path = get_legacy_asset_path(filename)
    if not path.exists():
        return None
    try:
        with Image.open(path) as img:
            return img.convert("RGB")
    except (OSError, UnidentifiedImageError):
        return None


def mm_to_px(mm: float, dpi: int = PRINTER_DPI) -> int:
    """Convert millimeters to pixels for a DPI."""
    return max(1, int(mm * dpi / 25.4))


def resize_for_legacy_printer_width(
    image: Image.Image,
    side_margin_mm: float = 0.0,
    print_width_mm: float = PRINT_WIDTH_MM,
) -> Image.Image:
    """Resize image to legacy printer width with optional side margins."""
    paper_width_px = mm_to_px(print_width_mm)
    inner_width_mm = max(1.0, print_width_mm - (2.0 * max(0.0, side_margin_mm)))
    inner_width_px = mm_to_px(inner_width_mm)

    w_percent = inner_width_px / float(image.size[0])
    height_px = max(1, int(float(image.size[1]) * w_percent))
    resized = image.resize((inner_width_px, height_px), Image.Resampling.LANCZOS)

    if side_margin_mm <= 0:
        return resized

    canvas = Image.new("RGB", (paper_width_px, height_px), "white")
    x = (paper_width_px - resized.width) // 2
    canvas.paste(resized, (x, 0))
    return canvas


def preprocess_reel_screenshot(image: Image.Image) -> Image.Image:
    """Crop reel screenshot to match legacy print framing.

    Steps:
    - Remove large black letterbox bands.
    - Trim a fixed top/bottom UI strip so the OpenGL/status overlays are removed.
    """
    img = image.convert("RGB")
    img = _crop_black_bars(img)

    h = img.height
    if h < 120:
        return img

    # More aggressive top trim to remove mirror/OpenGL/status overlays.
    top_crop = int(h * 0.10)
    bottom_crop = int(h * 0.04)
    if (h - top_crop - bottom_crop) > int(h * 0.45):
        img = img.crop((0, top_crop, img.width, h - bottom_crop))

    return img


def _crop_black_bars(image: Image.Image) -> Image.Image:
    """Remove thick top/bottom black bars from mirror captures."""
    gray = np.asarray(image.convert("L"))
    if gray.ndim != 2 or gray.shape[0] < 20:
        return image

    row_signal = (gray > 12).mean(axis=1)
    # Ignore sparse bright glyphs over black bars (e.g., OpenGL text).
    active_rows = np.where(row_signal > 0.08)[0]
    if active_rows.size < 10:
        return image

    top = int(active_rows[0])
    bottom = int(active_rows[-1]) + 1
    if bottom - top < int(image.height * 0.4):
        return image
    if top == 0 and bottom == image.height:
        return image
    return image.crop((0, top, image.width, bottom))


def placeholder_topic(reel_number: int, rng: random.Random | None = None) -> str:
    """Return a placeholder topic when LLM analysis is disabled."""
    if rng is not None:
        return rng.choice(REEL_TOPICS)
    return REEL_TOPICS[(reel_number - 1) % len(REEL_TOPICS)]


def build_summary_lines(entries: Iterable[ReelReceiptEntry], line_width: int = LINE_WIDTH) -> list[str]:
    """Build old-style itemized summary receipt lines."""
    line_width = max(24, int(line_width))
    items = sorted(entries, key=lambda entry: entry.reel_number)
    if not items:
        return ["NO REELS RECORDED"]

    total_s = sum(entry.duration_seconds for entry in items)
    avg_s = total_s / len(items)

    lines = ["REEL RECEIPT", "=" * line_width]
    for entry in items:
        right = f"${entry.duration_seconds:,.2f}"
        left = entry.topic
        lines.append(_fit_item_line(left, right, width=line_width))

    lines.append("=" * line_width)
    total_label = f"${total_s:,.2f}"
    lines.append(f"TOTAL{'.' * (line_width - 6 - len(total_label))}{total_label}")
    lines.append("=" * line_width)
    lines.append(f"You spent {total_s:.2f} seconds watching {len(items)} reels")
    lines.append(f"Average attention span: {avg_s:.2f}s")

    by_topic: defaultdict[str, float] = defaultdict(float)
    for entry in items:
        by_topic[entry.topic] += entry.duration_seconds
    max_topic, max_s = max(by_topic.items(), key=lambda kv: kv[1]) if by_topic else ("Unknown", 0.0)
    pct = (max_s / total_s * 100.0) if total_s else 0.0
    max_topic = _truncate_plain(max_topic, 20)
    peak_line = f"Peak fixation: {max_topic} - {max_s:.2f}s ({pct:.1f}%)"
    if len(peak_line) <= line_width:
        lines.append(peak_line)
    else:
        lines.append(f"Peak fixation: {max_topic} - {max_s:.2f}s")
        lines.append(f"({pct:.1f}%)")
    return _wrap_non_item_lines(lines, line_width)


def _truncate_plain(text: str, max_len: int) -> str:
    """Truncate plain text with ellipsis if needed."""
    clean = " ".join(text.split())
    if max_len <= 3:
        return clean[:max_len]
    if len(clean) <= max_len:
        return clean
    return clean[: max_len - 3].rstrip() + "..."


def _fit_item_line(left: str, right: str, width: int) -> str:
    """Compose `left.....right` while always keeping the right value visible."""
    min_dots = 1
    max_left = max(1, width - len(right) - min_dots)
    left_fit = _truncate_plain(left, max_left)
    dots = "." * max(min_dots, width - len(left_fit) - len(right))
    return f"{left_fit}{dots}{right}"


def _wrap_non_item_lines(lines: list[str], width: int) -> list[str]:
    """Hard-wrap long text lines while preserving itemized rows."""
    wrapped: list[str] = []
    for line in lines:
        if len(line) <= width:
            wrapped.append(line)
            continue
        if _OLD_REEL_ITEM_PATTERN.match(line) and "$" in line:
            wrapped.append(line[:width])
            continue
        if _NEW_REEL_ITEM_PATTERN.match(line):
            wrapped.append(line[:width])
            continue
        if _PLAIN_REEL_ITEM_PATTERN.match(line) and not line.startswith("TOTAL"):
            wrapped.append(line[:width])
            continue
        if line.startswith("TOTAL"):
            wrapped.append(line[:width])
            continue

        rest = line
        while len(rest) > width:
            split_at = rest.rfind(" ", 0, width + 1)
            if split_at <= 0:
                split_at = width
            wrapped.append(rest[:split_at].rstrip())
            rest = rest[split_at:].lstrip()
        if rest:
            wrapped.append(rest)
    return wrapped


def parse_topics_from_receipt_content(receipt_content: str | None) -> dict[int, str]:
    """Parse old/new summary item lines from stored receipt text."""
    if not receipt_content:
        return {}
    parsed: dict[int, str] = {}
    for raw_line in receipt_content.splitlines():
        line = raw_line.strip()
        old_match = _OLD_REEL_ITEM_PATTERN.match(line)
        if old_match:
            reel_number = int(old_match.group(1))
            topic = old_match.group(2).strip() or "Unknown"
            parsed[reel_number] = topic
            continue

        if not _NEW_REEL_ITEM_PATTERN.match(line):
            continue

        topic_match = re.match(r"^\[(.*?)\]", line)
        if not topic_match:
            continue
        topic = topic_match.group(1).strip() or "Unknown"
        parsed[len(parsed) + 1] = topic

    for raw_line in receipt_content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("TOTAL"):
            continue
        if _OLD_REEL_ITEM_PATTERN.match(line) or _NEW_REEL_ITEM_PATTERN.match(line):
            continue

        plain_match = _PLAIN_REEL_ITEM_PATTERN.match(line)
        if not plain_match:
            continue
        topic = plain_match.group(1).strip() or "Unknown"
        parsed[len(parsed) + 1] = topic
    return parsed


def play_legacy_audio(
    filename: str,
    timeout_seconds: float = 15.0,
    blocking: bool = False,
) -> bool:
    """Play audio asset if possible; fail silently if backend unavailable."""
    clip_path = get_legacy_asset_path(filename)
    if not clip_path.exists():
        return False

    for player in ("afplay", "aplay", "paplay"):
        if not shutil.which(player):
            continue
        try:
            if blocking:
                subprocess.run([player, str(clip_path)], check=False, timeout=timeout_seconds)
            else:
                subprocess.Popen(
                    [player, str(clip_path)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            return True
        except Exception:
            continue

    if not blocking:
        return False

    try:
        import pygame  # type: ignore

        pygame.mixer.init()
        pygame.mixer.music.load(str(clip_path))
        pygame.mixer.music.play()
        start = time.time()
        while pygame.mixer.music.get_busy() and (time.time() - start) < timeout_seconds:
            time.sleep(0.1)
        if pygame.mixer.music.get_busy():
            pygame.mixer.music.stop()
        pygame.mixer.quit()
        return True
    except Exception:
        return False
