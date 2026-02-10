"""ESC/POS thermal receipt printer implementation."""

import time
from datetime import datetime
from enum import Enum

from PIL import Image

from src.printing.base import BasePrinter
from src.printing.gemini_categorizer import GeminiCategorizer
from src.printing.legacy_format import (
    LINE_WIDTH,
    PRINT_WIDTH_MM,
    PRINTER_DPI,
    ReelReceiptEntry,
    SIDE_MARGIN_MM,
    build_summary_lines,
    load_legacy_image,
    mm_to_px,
    play_legacy_audio,
    preprocess_reel_screenshot,
)


class PrinterModel(Enum):
    """Known printer models with their USB IDs."""

    # Rongta printers (common vendor IDs)
    RONGTA_RP58 = (0x0483, 0x5743, 384, "Rongta RP58 (58mm)")
    RONGTA_RP80 = (0x0483, 0x5740, 576, "Rongta RP80 (80mm)")
    RONGTA_ACE_V1 = (0x6868, 0x0500, 576, "Rongta ACE V1 (80mm)")
    RONGTA_GENERIC = (0x0483, 0x5720, 384, "Rongta Generic")

    # Other common ESC/POS printers
    EPSON_TM_T20 = (0x04B8, 0x0E15, 576, "Epson TM-T20")
    EPSON_TM_T88 = (0x04B8, 0x0202, 576, "Epson TM-T88")

    def __init__(self, vendor_id: int, product_id: int, width: int, name: str):
        self.vendor_id = vendor_id
        self.product_id = product_id
        self.width = width
        self.display_name = name


class ESCPOSPrinter(BasePrinter):
    """Real thermal receipt printer using ESC/POS protocol."""

    # Common Rongta USB IDs to try
    RONGTA_USB_IDS = [
        (0x0483, 0x5743),  # RP58
        (0x0483, 0x5740),  # RP80
        (0x0483, 0x5720),  # Generic
        (0x6868, 0x0500),  # ACE V1
        (0x6868, 0x0200),  # Alternative
        (0x0416, 0x5011),  # Some Rongta models
        (0x0483, 0x070B),  # RP328
    ]

    def __init__(
        self,
        device_path: str | None = None,
        printer_width: int = mm_to_px(PRINT_WIDTH_MM, PRINTER_DPI),
        vendor_id: int | None = None,
        product_id: int | None = None,
        model: PrinterModel | None = None,
        auto_detect: bool = True,
    ) -> None:
        """Initialize ESC/POS printer.

        Args:
            device_path: Path to printer device (for serial/file connection).
            printer_width: Printer width in pixels (58mm=384, 80mm=576).
            vendor_id: USB vendor ID (for USB connection).
            product_id: USB product ID (for USB connection).
            model: Specific printer model preset.
            auto_detect: Try to auto-detect Rongta printer if no IDs given.
        """
        self.device_path = device_path
        self.printer_width = printer_width
        self.vendor_id = vendor_id
        self.product_id = product_id
        self.auto_detect = auto_detect
        self._printer = None
        self._reel_entries: dict[int, ReelReceiptEntry] = {}
        self._categorizer = GeminiCategorizer(max_workers=4)

        # Apply model preset if given
        if model:
            self.vendor_id = model.vendor_id
            self.product_id = model.product_id
            self.printer_width = model.width

        self._connect()

    def _connect(self) -> None:
        """Connect to the printer."""
        try:
            from escpos.printer import Usb, File

            # Try USB connection with specific IDs
            if self.vendor_id and self.product_id:
                self._printer = Usb(self.vendor_id, self.product_id)
                return

            # Try auto-detect Rongta printers
            if self.auto_detect:
                for vid, pid in self.RONGTA_USB_IDS:
                    try:
                        self._printer = Usb(vid, pid)
                        print(f"Found Rongta printer: VID=0x{vid:04X}, PID=0x{pid:04X}")
                        return
                    except Exception:
                        continue

            # Fall back to file/device path
            if self.device_path:
                self._printer = File(self.device_path)
            else:
                raise RuntimeError(
                    "No printer found. Specify --vendor-id/--product-id or --printer-device"
                )

        except Exception as e:
            raise RuntimeError(f"Failed to connect to printer: {e}") from e

    @classmethod
    def find_usb_printers(cls) -> list[tuple[int, int, str]]:
        """Find connected USB printers.

        Returns:
            List of (vendor_id, product_id, description) tuples.
        """
        printers = []
        try:
            import usb.core

            # Find all USB devices
            devices = usb.core.find(find_all=True)
            for dev in devices:
                # Check if it might be a printer (class 7) or vendor-specific
                try:
                    desc = f"VID=0x{dev.idVendor:04X} PID=0x{dev.idProduct:04X}"
                    # Check known Rongta IDs
                    for vid, pid in cls.RONGTA_USB_IDS:
                        if dev.idVendor == vid and dev.idProduct == pid:
                            desc += " (Rongta)"
                            break
                    printers.append((dev.idVendor, dev.idProduct, desc))
                except Exception:
                    continue
        except ImportError:
            pass
        except Exception:
            pass

        return printers

    def _prepare_image(self, image: Image.Image, side_margin_mm: float = 0.0) -> Image.Image:
        """Prepare image for thermal printing with optional side margins."""
        paper_width_px = int(self.printer_width)
        side_margin_px = mm_to_px(side_margin_mm, PRINTER_DPI) if side_margin_mm > 0 else 0
        inner_width_px = max(1, paper_width_px - (2 * side_margin_px))

        w_percent = inner_width_px / float(image.size[0])
        height_px = max(1, int(float(image.size[1]) * w_percent))
        resized = image.resize((inner_width_px, height_px), Image.Resampling.LANCZOS).convert("1")
        if side_margin_px <= 0:
            return resized

        canvas = Image.new("1", (paper_width_px, height_px), 1)
        x = (paper_width_px - resized.width) // 2
        canvas.paste(resized, (x, 0))
        return canvas

    def _print_legacy_asset(self, asset_name: str) -> None:
        if not self._printer:
            return
        asset_img = load_legacy_image(asset_name)
        if asset_img is None:
            return
        self._printer.image(self._prepare_image(asset_img))

    def _safe_feed(self, lines: int) -> None:
        if not self._printer:
            return
        try:
            self._printer.print_and_feed(lines)
        except Exception:
            try:
                self._printer.feed(lines)
            except Exception:
                pass

    def print_header(self, session_start: str) -> None:
        if not self._printer:
            return

        self._print_legacy_asset("header.png")

    def print_reel(self, screenshot: Image.Image, duration_seconds: float, reel_number: int) -> None:
        if not self._printer:
            return

        processed = preprocess_reel_screenshot(screenshot)
        self._categorizer.submit(reel_number=reel_number, screenshot=processed)
        topic = "Processing..."
        self._reel_entries[reel_number] = ReelReceiptEntry(
            reel_number=reel_number,
            duration_seconds=duration_seconds,
            topic=topic,
        )

        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._printer.set(align="center", bold=False, width=1, height=1)
        self._printer.text(f"Started: {ts}\n")

        self._printer.image(self._prepare_image(processed, side_margin_mm=SIDE_MARGIN_MM))

        self._printer.set(align="center", bold=True, width=1, height=1)
        self._printer.text(f"Time Spent: {duration_seconds:.2f}s\n")
        self._printer.set(align="left", bold=False, width=1, height=1)

    def print_summary(self, total_reels: int, total_time_seconds: float) -> None:
        if not self._printer:
            return

        # Must wait for all Gemini calls before final receipt is printed.
        topics = self._categorizer.wait_for_all()
        for reel_number, topic in topics.items():
            if reel_number in self._reel_entries and topic:
                self._reel_entries[reel_number].topic = topic

        self._print_legacy_asset("art.png")
        self._print_legacy_asset("summary.png")

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
        fed_after_totals = False

        for idx, line in enumerate(lines):
            if idx == 0 and line == "REEL RECEIPT":
                self._printer.set(align="center", bold=True, double_width=True, double_height=True)
                self._printer.text(f"{line}\n")
                self._printer.set(align="left", bold=False, double_width=False, double_height=False)
                continue

            if line == "NO REELS RECORDED":
                self._printer.set(align="center", bold=True, double_width=True, double_height=True)
                self._printer.text(f"{line}\n")
                self._printer.set(align="left", bold=False, double_width=False, double_height=False)
                continue

            if line.startswith("TOTAL"):
                self._printer.set(align="left", bold=True, double_width=False, double_height=False)
                self._printer.text(f"{line}\n")
                self._printer.set(align="left", bold=False, double_width=False, double_height=False)
                continue

            if not fed_after_totals and line.startswith("You spent"):
                self._safe_feed(1)
                fed_after_totals = True

            self._printer.set(align="left", bold=False, double_width=False, double_height=False)
            self._printer.text(f"{line}\n")

        self._print_legacy_asset("footer.png")
        self._safe_feed(6)
        time.sleep(1.0)
        play_legacy_audio("waitaudio.wav", blocking=False)
        self._printer.set(align="left", bold=False, double_width=False, double_height=False)

    def cut(self) -> None:
        """Cut the receipt paper."""
        if not self._printer:
            return

        self._printer.cut()

    def close(self) -> None:
        """Close the printer connection."""
        self._categorizer.close()
        if self._printer:
            try:
                self._printer.close()
            except Exception:
                pass
            self._printer = None
