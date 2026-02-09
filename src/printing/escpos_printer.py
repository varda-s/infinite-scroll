"""ESC/POS thermal receipt printer implementation."""

from datetime import datetime
from enum import Enum

from PIL import Image

from src.printing.base import BasePrinter


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
        printer_width: int = 384,
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

    def _prepare_image(self, image: Image.Image) -> Image.Image:
        """Prepare image for thermal printing.

        Args:
            image: Original image.

        Returns:
            Resized and converted image.
        """
        # Calculate new height maintaining aspect ratio
        aspect_ratio = image.height / image.width
        new_height = int(self.printer_width * aspect_ratio)

        # Resize image
        image = image.resize((self.printer_width, new_height), Image.Resampling.LANCZOS)

        # Convert to mode suitable for thermal printing
        image = image.convert("1")  # 1-bit pixels (black and white)

        return image

    def print_header(self, session_start: str) -> None:
        """Print session header."""
        if not self._printer:
            return

        self._printer.set(align="center", bold=True, double_height=True)
        self._printer.text("INSTAGRAM REEL TRACKER\n")
        self._printer.set(align="center", bold=False, double_height=False)
        self._printer.text("=" * 32 + "\n")
        self._printer.text(f"Session: {session_start}\n")
        self._printer.text("-" * 32 + "\n\n")

    def print_reel(self, screenshot: Image.Image, duration_seconds: float, reel_number: int) -> None:
        """Print a reel receipt with screenshot and duration."""
        if not self._printer:
            return

        # Reel header
        self._printer.set(align="center", bold=True)
        self._printer.text(f"REEL #{reel_number}\n")
        self._printer.set(bold=False)
        self._printer.text("-" * 32 + "\n")

        # Print screenshot
        prepared_image = self._prepare_image(screenshot)
        self._printer.image(prepared_image)

        # Print duration
        self._printer.text("\n")
        self._printer.text("-" * 32 + "\n")
        duration_str = self.format_duration(duration_seconds)
        self._printer.set(align="center", bold=True)
        self._printer.text(f"Time spent: {duration_str}\n")
        self._printer.set(bold=False)
        self._printer.text("-" * 32 + "\n\n")

    def print_summary(self, total_reels: int, total_time_seconds: float) -> None:
        """Print session summary."""
        if not self._printer:
            return

        self._printer.text("\n")
        self._printer.set(align="center", bold=True, double_height=True)
        self._printer.text("SESSION COMPLETE\n")
        self._printer.set(bold=False, double_height=False)
        self._printer.text("=" * 32 + "\n")

        self._printer.set(align="left")
        self._printer.text(f"Total reels: {total_reels}\n")
        self._printer.text(f"Total time: {self.format_duration(total_time_seconds)}\n")

        if total_reels > 0:
            avg_time = total_time_seconds / total_reels
            self._printer.text(f"Avg per reel: {self.format_duration(avg_time)}\n")

        self._printer.text("=" * 32 + "\n\n")

        # Thank you message
        self._printer.set(align="center", bold=True)
        self._printer.text("THANK YOU FOR SCROLLING!\n\n")
        self._printer.set(bold=False)
        self._printer.text("Maybe go outside for a bit? :)\n")
        self._printer.text("-" * 32 + "\n")

        # Print timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._printer.text(f"\n{timestamp}\n\n")

    def cut(self) -> None:
        """Cut the receipt paper."""
        if not self._printer:
            return

        self._printer.cut()

    def close(self) -> None:
        """Close the printer connection."""
        if self._printer:
            try:
                self._printer.close()
            except Exception:
                pass
            self._printer = None
