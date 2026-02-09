"""Mock printer for testing - outputs to console and files."""

from datetime import datetime
from pathlib import Path

from PIL import Image

from src.printing.base import BasePrinter


class MockPrinter(BasePrinter):
    """Mock printer that saves output to files and prints ASCII art to console."""

    def __init__(self, output_dir: Path, verbose: bool = True) -> None:
        """Initialize mock printer.

        Args:
            output_dir: Directory to save output files.
            verbose: Whether to print to console.
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.verbose = verbose
        self._receipt_lines: list[str] = []
        self._reel_count = 0
        self._session_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    def _log(self, message: str) -> None:
        """Log message to console if verbose."""
        if self.verbose:
            print(message)

    def _add_receipt_line(self, line: str) -> None:
        """Add line to receipt buffer."""
        self._receipt_lines.append(line)
        self._log(line)

    def _image_to_ascii(self, image: Image.Image, width: int = 40) -> str:
        """Convert image to ASCII art.

        Args:
            image: PIL Image to convert.
            width: Width in characters.

        Returns:
            ASCII art string.
        """
        # Resize image maintaining aspect ratio
        aspect_ratio = image.height / image.width
        height = int(width * aspect_ratio * 0.5)  # 0.5 because chars are taller than wide
        image = image.resize((width, height))

        # Convert to grayscale
        image = image.convert("L")

        # ASCII characters from darkest to lightest
        ascii_chars = "@%#*+=-:. "

        # Convert pixels to ASCII
        pixels = list(image.getdata())
        ascii_str = ""
        for i, pixel in enumerate(pixels):
            ascii_str += ascii_chars[pixel * len(ascii_chars) // 256]
            if (i + 1) % width == 0:
                ascii_str += "\n"

        return ascii_str

    def print_header(self, session_start: str) -> None:
        """Print session header."""
        self._add_receipt_line("=" * 42)
        self._add_receipt_line("        INSTAGRAM REEL TRACKER")
        self._add_receipt_line("=" * 42)
        self._add_receipt_line(f"  Session started: {session_start}")
        self._add_receipt_line("-" * 42)

    def print_reel(self, screenshot: Image.Image, duration_seconds: float, reel_number: int) -> None:
        """Print a reel receipt with screenshot and duration."""
        self._reel_count += 1

        # Save screenshot to file
        screenshot_path = self.output_dir / f"reel_{self._session_id}_{reel_number:04d}.png"
        screenshot.save(screenshot_path)

        # Print receipt
        self._add_receipt_line("")
        self._add_receipt_line(f"  REEL #{reel_number}")
        self._add_receipt_line("-" * 42)

        # Convert to ASCII and print
        ascii_art = self._image_to_ascii(screenshot)
        for line in ascii_art.strip().split("\n"):
            self._add_receipt_line(f"  {line}")

        self._add_receipt_line("-" * 42)
        duration_str = self.format_duration(duration_seconds)
        self._add_receipt_line(f"  Time spent: {duration_str}")
        self._add_receipt_line(f"  Screenshot: {screenshot_path.name}")
        self._add_receipt_line("-" * 42)

    def print_summary(self, total_reels: int, total_time_seconds: float) -> None:
        """Print session summary."""
        self._add_receipt_line("")
        self._add_receipt_line("=" * 42)
        self._add_receipt_line("           SESSION COMPLETE")
        self._add_receipt_line("=" * 42)
        self._add_receipt_line(f"  Total reels viewed: {total_reels}")
        self._add_receipt_line(f"  Total time: {self.format_duration(total_time_seconds)}")

        if total_reels > 0:
            avg_time = total_time_seconds / total_reels
            self._add_receipt_line(f"  Avg time per reel: {self.format_duration(avg_time)}")

        self._add_receipt_line("")
        self._add_receipt_line("-" * 42)
        self._add_receipt_line("      THANK YOU FOR SCROLLING!")
        self._add_receipt_line("")
        self._add_receipt_line("   Maybe go outside for a bit? :)")
        self._add_receipt_line("-" * 42)
        self._add_receipt_line("=" * 42)
        self._add_receipt_line("")

    def cut(self) -> None:
        """Simulate paper cut."""
        self._add_receipt_line("")
        self._add_receipt_line("✂" + "-" * 40 + "✂")
        self._add_receipt_line("")

    def close(self) -> None:
        """Save receipt to file."""
        receipt_path = self.output_dir / f"receipt_{self._session_id}.txt"
        with open(receipt_path, "w") as f:
            f.write("\n".join(self._receipt_lines))

        if self.verbose:
            print(f"\n[MockPrinter] Receipt saved to: {receipt_path}")

    def get_receipt_content(self) -> str:
        """Get the current receipt content as a string."""
        return "\n".join(self._receipt_lines)
