"""ESC/POS thermal receipt printer implementation."""

import time
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
    SUMMARY_LINE_WIDTH,
    build_summary_lines,
    load_legacy_image,
    mm_to_px,
    play_legacy_audio,
    preprocess_reel_screenshot,
)
from src.time_utils import format_receipt_timestamp


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
        (0x0FE6, 0x811E),  # Legacy tested booth printer (known working)
        (0x0483, 0x5743),  # RP58
        (0x0483, 0x5740),  # RP80
        (0x0483, 0x5720),  # Generic
        (0x6868, 0x0500),  # ACE V1
        (0x6868, 0x0200),  # Alternative
        (0x0416, 0x5011),  # Some Rongta models
        (0x0483, 0x070B),  # RP328
    ]

    @staticmethod
    def _ensure_usb_device_ready(printer: object) -> None:
        """Force lazy USB printers to resolve a real device handle."""
        try:
            device = getattr(printer, "device")
        except Exception as e:
            raise RuntimeError(f"USB backend unavailable: {e}") from e

        if device is None:
            raise RuntimeError("USB printer handle was not created")

    @classmethod
    def can_connect(cls) -> bool:
        """Return True when a supported Rongta printer is reachable."""
        try:
            from escpos.printer import Usb

            for vid, pid in cls.RONGTA_USB_IDS:
                printer = None
                try:
                    printer = Usb(vid, pid)
                    cls._ensure_usb_device_ready(printer)
                    return True
                except Exception:
                    continue
                finally:
                    try:
                        if printer is not None:
                            printer.close()
                    except Exception:
                        pass
        except Exception:
            pass

        return False

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
                self._ensure_usb_device_ready(self._printer)
                self._configure_profile_width()
                self._reset_printer()
                return

            # Try auto-detect Rongta printers
            if self.auto_detect:
                for vid, pid in self.RONGTA_USB_IDS:
                    try:
                        self._printer = Usb(vid, pid)
                        self._ensure_usb_device_ready(self._printer)
                        self._configure_profile_width()
                        print(f"Found Rongta printer: VID=0x{vid:04X}, PID=0x{pid:04X}")
                        self._reset_printer()
                        return
                    except Exception:
                        continue

            # Fall back to file/device path
            if self.device_path:
                self._printer = File(self.device_path)
                self._configure_profile_width()
                self._reset_printer()
            else:
                raise RuntimeError(
                    "No printer found. Specify --vendor-id/--product-id or --printer-device"
                )

        except Exception as e:
            raise RuntimeError(f"Failed to connect to printer: {e}") from e

    def _configure_profile_width(self) -> None:
        """Populate profile width so python-escpos image logging stays quiet."""
        if not self._printer:
            return
        try:
            media = self._printer.profile.profile_data.setdefault("media", {})
            width = media.setdefault("width", {})
            width["pixels"] = str(int(self.printer_width))
        except Exception:
            pass

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

    def _reset_printer(self) -> None:
        """Hard reset printer state using ESC/POS initialize."""
        if not self._printer:
            return
        try:
            self._printer._raw(b"\x1b@")
        except Exception:
            pass
        self._reset_style()

    @staticmethod
    def _align_code(align: str) -> int:
        return {"left": 0, "center": 1, "right": 2}.get(align, 0)

    def _set_style(self, align: str = "left", bold: bool = False, width: int = 1, height: int = 1) -> None:
        """Force style with both driver API and raw ESC/POS commands."""
        if not self._printer:
            return
        try:
            self._printer.set(align=align, bold=bold, width=width, height=height)
        except TypeError:
            pass
        except Exception:
            pass

        try:
            self._printer.set(align=align, width=width, height=height)
        except Exception:
            pass

        try:
            self._printer._raw(b"\x1ba" + bytes([self._align_code(align)]))
            self._printer._raw(b"\x1bE" + (b"\x01" if bold else b"\x00"))
            size = max(0, width - 1) << 4 | max(0, height - 1)
            self._printer._raw(b"\x1d!" + bytes([size]))
        except Exception:
            pass

    def _reset_style(self) -> None:
        """Force printer back to normal text mode."""
        if not self._printer:
            return
        try:
            self._printer.set(align="left", width=1, height=1, bold=False)
        except Exception:
            pass

        try:
            self._printer._raw(b"\x1ba\x00")
            self._printer._raw(b"\x1bE\x00")
            self._printer._raw(b"\x1d!\x00")
        except Exception:
            pass

    def _text_line(
        self,
        text: str,
        align: str = "left",
        bold: bool = False,
        dbl_width: bool = False,
        dbl_height: bool = False,
    ) -> None:
        """Print one text line and always reset style afterward."""
        if not self._printer:
            return
        try:
            self._set_style(
                align=align,
                bold=bold,
                width=2 if dbl_width else 1,
                height=2 if dbl_height else 1,
            )
            self._printer.text(f"{text}\n")
        finally:
            self._reset_style()

    def _print_legacy_asset(self, asset_name: str) -> None:
        if not self._printer:
            return
        asset_img = load_legacy_image(asset_name)
        if asset_img is None:
            return
        self._reset_style()
        self._printer.image(self._prepare_image(asset_img))
        self._reset_style()

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

    def print_reel(
        self,
        screenshot: Image.Image,
        duration_seconds: float,
        reel_number: int,
        analysis_frames: list[Image.Image] | None = None,
    ) -> None:
        if not self._printer:
            return

        processed = preprocess_reel_screenshot(screenshot)
        self._categorizer.submit(
            reel_number=reel_number,
            screenshot=processed,
            analysis_frames=analysis_frames,
        )
        topic = "Processing..."
        self._reel_entries[reel_number] = ReelReceiptEntry(
            reel_number=reel_number,
            duration_seconds=duration_seconds,
            topic=topic,
        )

        ts = format_receipt_timestamp()
        self._text_line(f"Started: {ts}", align="center", bold=False)

        self._reset_style()
        self._printer.image(self._prepare_image(processed, side_margin_mm=0.0))
        self._reset_style()
        self._safe_feed(1)

        self._text_line(f"Time Spent: {duration_seconds:.2f}s", align="center", bold=True)

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

        lines = build_summary_lines(entries, line_width=SUMMARY_LINE_WIDTH)
        fed_after_totals = False

        for idx, line in enumerate(lines):
            if idx == 0 and line == "REEL RECEIPT":
                self._text_line(line, align="center", bold=True, dbl_width=False, dbl_height=False)
                continue

            if line == "NO REELS RECORDED":
                self._text_line(line, align="center", bold=True, dbl_width=False, dbl_height=False)
                continue

            if line.startswith("TOTAL"):
                self._text_line(line, align="left", bold=True, dbl_width=False, dbl_height=False)
                continue

            if not fed_after_totals and line.startswith("You spent"):
                self._safe_feed(1)
                fed_after_totals = True

            self._text_line(line, align="left", bold=False, dbl_width=False, dbl_height=False)

        self._print_legacy_asset("footer.png")
        self._safe_feed(6)
        time.sleep(1.0)
        play_legacy_audio("waitaudio.wav", blocking=False)
        self._reset_style()

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
