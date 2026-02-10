"""Entry point for the Instagram Reel Tracker."""

import argparse
import sys
from pathlib import Path

from src.config import Config
from src.capture.base import BaseCapture
from src.capture.device_detector import DeviceDetector
from src.capture.mirror_capture import MirrorCapture
from src.capture.mock_capture import MockCapture
from src.printing.base import BasePrinter
from src.printing.mock_printer import MockPrinter
from src.printing.escpos_printer import ESCPOSPrinter
from src.orchestrator import Orchestrator


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Instagram Reel Tracker - Track time spent on reels",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start the web UI (default)
  python3 -m src.main

  # Start in CLI mode
  python -m src.main --cli

  # CLI: Use mock capture from video file
  python -m src.main --cli --mock-capture video.mp4

  # CLI: Use Rongta receipt printer (auto-detect)
  python -m src.main --cli --printer rongta

  # CLI: Use Rongta with specific USB IDs
  python -m src.main --cli --printer escpos --vendor-id 0x0483 --product-id 0x5743
  # CLI: Use legacy tested booth IDs
  python -m src.main --cli --printer escpos --vendor-id 0x0fe6 --product-id 0x811e

  # Find your printer's USB IDs
  python -m src.main --list-printers
        """,
    )

    # Mode selection
    parser.add_argument(
        "--cli",
        action="store_true",
        help="Run in CLI mode instead of web UI",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port for web UI (default: 8080)",
    )

    # Device selection
    parser.add_argument(
        "--mock-capture",
        type=Path,
        metavar="PATH",
        help="Use mock capture from video file or image directory",
    )

    # Capture settings
    parser.add_argument(
        "--fps",
        type=int,
        default=20,
        help="Capture frame rate (default: 20)",
    )

    # Detection settings
    parser.add_argument(
        "--hash-threshold",
        type=int,
        default=15,
        help="Hash difference threshold for new reel detection (default: 15)",
    )
    parser.add_argument(
        "--min-duration",
        type=float,
        default=0.5,
        help="Minimum reel duration in seconds (default: 0.5)",
    )

    # Printer settings
    parser.add_argument(
        "--printer",
        type=str,
        choices=["mock", "escpos", "rongta"],
        default="mock",
        help="Printer type: mock, escpos, or rongta (default: mock)",
    )
    parser.add_argument(
        "--printer-device",
        type=str,
        help="Printer device path (e.g., /dev/usb/lp0)",
    )
    parser.add_argument(
        "--vendor-id",
        type=lambda x: int(x, 0),  # Supports 0x prefix
        help="USB Vendor ID for printer (e.g., 0x0483)",
    )
    parser.add_argument(
        "--product-id",
        type=lambda x: int(x, 0),  # Supports 0x prefix
        help="USB Product ID for printer (e.g., 0x5743)",
    )
    parser.add_argument(
        "--printer-width",
        type=int,
        choices=[58, 80],
        default=58,
        help="Printer paper width in mm (default: 58)",
    )

    # Output settings
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output"),
        help="Output directory for mock printer (default: output)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress console output from mock printer",
    )

    # Utility
    parser.add_argument(
        "--list-devices",
        action="store_true",
        help="List connected phones and exit",
    )
    parser.add_argument(
        "--list-printers",
        action="store_true",
        help="List USB printers and show their IDs",
    )

    return parser.parse_args()


def list_devices() -> None:
    """List all connected devices."""
    print("Detecting connected iPhones via screen mirroring...\n")

    devices = DeviceDetector.detect_all_devices()

    if not devices:
        print("No iPhone mirrors found.")
        print("\nTo connect your iPhone:")
        print("  1. Connect iPhone to Mac via USB cable")
        print("  2. Tap 'Trust' on iPhone when prompted")
        print("  3. Open QuickTime Player")
        print("  4. Go to File → New Movie Recording")
        print("  5. Click the arrow next to record and select your iPhone")
        return

    print(f"Found {len(devices)} device(s):\n")
    for device in devices:
        print(f"  [iPhone Mirror] {device.device_name}")
        print(f"    ID: {device.device_id}")
        if device.model:
            print(f"    App: {device.model}")
        print()


def list_printers() -> None:
    """List USB printers and their IDs."""
    print("Searching for USB printers...\n")
    print("Known Rongta USB IDs:")
    print("  Legacy Booth:   VID=0x0FE6, PID=0x811E")
    print("  RP58 (58mm):  VID=0x0483, PID=0x5743")
    print("  RP80 (80mm):  VID=0x0483, PID=0x5740")
    print("  ACE V1:       VID=0x6868, PID=0x0500")
    print("  Generic:      VID=0x0483, PID=0x5720")
    print()

    try:
        import usb.core

        print("Scanning USB devices...\n")
        devices = list(usb.core.find(find_all=True))

        if not devices:
            print("No USB devices found.")
            return

        # Filter for likely printers
        printer_classes = {7}  # Printer class
        rongta_vendors = {0x0FE6, 0x0483, 0x6868, 0x0416}

        print("Potential printers found:\n")
        found_any = False

        for dev in devices:
            is_rongta = dev.idVendor in rongta_vendors
            try:
                # Check device class
                is_printer_class = dev.bDeviceClass == 7
                # Check interface classes
                for cfg in dev:
                    for intf in cfg:
                        if intf.bInterfaceClass == 7:
                            is_printer_class = True
                            break
            except Exception:
                is_printer_class = False

            if is_rongta or is_printer_class:
                found_any = True
                label = " (Rongta)" if is_rongta else ""
                print(f"  Vendor ID:  0x{dev.idVendor:04X}")
                print(f"  Product ID: 0x{dev.idProduct:04X}{label}")
                try:
                    if dev.manufacturer:
                        print(f"  Manufacturer: {dev.manufacturer}")
                    if dev.product:
                        print(f"  Product: {dev.product}")
                except Exception:
                    pass
                print()

        if not found_any:
            print("No printers detected. Your printer may use different USB IDs.")
            print("\nTo find your printer manually on macOS/Linux:")
            print("  lsusb  (install with: brew install lsusb)")
            print("  OR: system_profiler SPUSBDataType")
            print("\nThen use: --vendor-id 0xXXXX --product-id 0xYYYY")

    except ImportError:
        print("USB scanning requires pyusb. Install with: pip install pyusb")
        print("\nAlternatively, find your printer IDs manually:")
        print("  macOS: system_profiler SPUSBDataType")
        print("  Linux: lsusb")
        print("\nThen use: --vendor-id 0xXXXX --product-id 0xYYYY")


def create_capture(args: argparse.Namespace) -> BaseCapture:
    """Create capture instance based on arguments.

    Args:
        args: Parsed command line arguments.

    Returns:
        Configured capture instance.
    """
    if args.mock_capture:
        return MockCapture(source=args.mock_capture)

    # Use iPhone-to-Mac mirroring connector
    return MirrorCapture()


def create_printer(args: argparse.Namespace) -> BasePrinter:
    """Create printer instance based on arguments.

    Args:
        args: Parsed command line arguments.

    Returns:
        Configured printer instance.
    """
    if args.printer == "mock":
        return MockPrinter(
            output_dir=args.output_dir,
            verbose=not args.quiet,
        )

    # Calculate pixel width from paper width
    # 58mm paper = 384 pixels, 80mm paper = 576 pixels
    pixel_width = 384 if args.printer_width == 58 else 576

    if args.printer == "rongta":
        # Rongta with auto-detection
        return ESCPOSPrinter(
            device_path=args.printer_device,
            printer_width=pixel_width,
            vendor_id=args.vendor_id,
            product_id=args.product_id,
            auto_detect=True,
        )

    elif args.printer == "escpos":
        # Generic ESC/POS - require explicit IDs or device path
        if not args.vendor_id and not args.product_id and not args.printer_device:
            print("ESC/POS printer requires --vendor-id/--product-id or --printer-device")
            print("Use --list-printers to find your printer's USB IDs")
            print("Or use --printer rongta for auto-detection")
            sys.exit(1)

        return ESCPOSPrinter(
            device_path=args.printer_device,
            printer_width=pixel_width,
            vendor_id=args.vendor_id,
            product_id=args.product_id,
            auto_detect=False,
        )

    else:
        print(f"Unknown printer type: {args.printer}")
        sys.exit(1)


def run_cli(args: argparse.Namespace) -> None:
    """Run in CLI mode."""
    # Create config
    config = Config(
        capture_fps=args.fps,
        hash_threshold=args.hash_threshold,
        min_reel_duration=args.min_duration,
        printer_type=args.printer,
        printer_device=args.printer_device or "/dev/usb/lp0",
        output_dir=args.output_dir,
        mock_capture_source=args.mock_capture,
    )

    # Create components
    capture = create_capture(args)
    printer = create_printer(args)

    # Create and run orchestrator
    orchestrator = Orchestrator(
        capture=capture,
        printer=printer,
        config=config,
    )

    print("=" * 50)
    print("  Instagram Reel Tracker (CLI Mode)")
    print("=" * 50)
    print()

    orchestrator.run()


def run_ui(port: int = 8080) -> None:
    """Run the web UI."""
    from src.ui.app import run
    run(port=port)


def main() -> None:
    """Main entry point."""
    args = parse_args()

    # Handle utility commands
    if args.list_devices:
        list_devices()
        return

    if args.list_printers:
        list_printers()
        return

    # Run in appropriate mode
    if args.cli:
        run_cli(args)
    else:
        print("=" * 50)
        print("  Instagram Reel Tracker")
        print("=" * 50)
        print()
        print(f"Starting web UI on http://127.0.0.1:{args.port}")
        print("Press Ctrl+C to stop")
        print()
        run_ui(port=args.port)


if __name__ == "__main__":
    main()
