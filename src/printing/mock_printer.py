"""Mock printer that mirrors legacy `screentimecode` receipt flow."""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

from PIL import Image

from src.printing.base import BasePrinter
from src.printing.gemini_categorizer import GeminiCategorizer
from src.printing.legacy_format import (
    LINE_WIDTH,
    ReelReceiptEntry,
    SIDE_MARGIN_MM,
    build_summary_lines,
    load_legacy_image,
    play_legacy_audio,
    preprocess_reel_screenshot,
    resize_for_legacy_printer_width,
)


class MockPrinter(BasePrinter):
    """Mock printer that saves receipt text and image artifacts to disk."""

    def __init__(self, output_dir: Path, verbose: bool = True) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.verbose = verbose
        self._receipt_lines: list[str] = []
        self._session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._reel_entries: dict[int, ReelReceiptEntry] = {}
        self._categorizer = GeminiCategorizer(max_workers=4)

    def _log(self, message: str) -> None:
        if self.verbose:
            print(message)

    def _add_receipt_line(self, line: str) -> None:
        self._receipt_lines.append(line)
        self._log(line)

    def _save_print_image(self, image: Image.Image, stem: str) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        out_path = self.output_dir / f"{stem}_{self._session_id}.png"
        resize_for_legacy_printer_width(image).save(out_path)
        return out_path

    def _print_legacy_asset(self, asset_name: str, stem: str) -> None:
        image = load_legacy_image(asset_name)
        if image is None:
            return
        out_path = self._save_print_image(image, stem)
        self._add_receipt_line(f"[IMAGE] {out_path.name}")

    def print_header(self, session_start: str) -> None:
        self._print_legacy_asset("header.png", "header")

    def print_reel(self, screenshot: Image.Image, duration_seconds: float, reel_number: int) -> None:
        processed = preprocess_reel_screenshot(screenshot)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        screenshot_path = self.output_dir / f"reel_{self._session_id}_{reel_number:04d}.png"
        resize_for_legacy_printer_width(processed, side_margin_mm=SIDE_MARGIN_MM).save(screenshot_path)

        # Start Gemini classification in parallel; topic is populated before summary print.
        self._categorizer.submit(reel_number=reel_number, screenshot=processed)
        topic = "Processing..."
        self._reel_entries[reel_number] = ReelReceiptEntry(
            reel_number=reel_number,
            duration_seconds=duration_seconds,
            topic=topic,
        )

        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._add_receipt_line(f"Started: {ts}")
        self._add_receipt_line(f"[IMAGE] {screenshot_path.name}")
        self._add_receipt_line(f"Time Spent: {duration_seconds:.2f}s")

    def print_summary(self, total_reels: int, total_time_seconds: float) -> None:
        # Must wait for all Gemini calls before final receipt is printed.
        topics = self._categorizer.wait_for_all()
        for reel_number, topic in topics.items():
            if reel_number in self._reel_entries and topic:
                self._reel_entries[reel_number].topic = topic

        self._print_legacy_asset("art.png", "art")
        self._print_legacy_asset("summary.png", "summary")

        entries = list(self._reel_entries.values())
        if not entries and total_reels > 0:
            avg_duration = total_time_seconds / total_reels
            entries = [
                ReelReceiptEntry(
                    reel_number=i + 1,
                    duration_seconds=avg_duration,
                    topic="Unlabeled",
                )
                for i in range(total_reels)
            ]

        lines = build_summary_lines(entries, line_width=LINE_WIDTH)
        for line in lines:
            self._add_receipt_line(line)

        self._print_legacy_asset("footer.png", "footer")
        # End-of-session processing cue (no startup audio).
        time.sleep(1.0)
        play_legacy_audio("waitaudio.wav", blocking=False)

    def cut(self) -> None:
        self._add_receipt_line("")
        self._add_receipt_line("✂" + "-" * 40 + "✂")
        self._add_receipt_line("")

    def close(self) -> None:
        self._categorizer.close()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        receipt_path = self.output_dir / f"receipt_{self._session_id}.txt"
        with open(receipt_path, "w", encoding="utf-8") as f:
            f.write("\n".join(self._receipt_lines))

        if self.verbose:
            print(f"\n[MockPrinter] Receipt saved to: {receipt_path}")

    def get_receipt_content(self) -> str:
        return "\n".join(self._receipt_lines)
