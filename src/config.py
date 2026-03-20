"""Configuration management for the Instagram Reel Tracker."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from src.detection.reel_detector import ReelDetectorConfig


@dataclass
class Config:
    """Application configuration."""

    # Capture settings
    capture_fps: int = 30
    capture_timeout: float = 5.0  # Timeout for device operations

    # Detection settings
    hash_threshold: int = 15  # pHash difference threshold for new reel
    min_reel_duration: float = 0.5  # Ignore very short "reels" (scroll-through)
    reel_detector: ReelDetectorConfig = field(default_factory=ReelDetectorConfig)

    # Instagram detection
    instagram_package: str = "com.instagram.android"  # Android package name
    instagram_bundle_id: str = "com.burbn.instagram"  # iOS bundle ID

    # Printer settings
    printer_type: Literal["mock", "escpos"] = "mock"
    printer_device: str = "/dev/usb/lp0"  # For real printer
    printer_width: int = 384  # Thermal printer width in pixels (48mm * 8 dots/mm)

    # Output settings
    output_dir: Path = field(default_factory=lambda: Path("output"))
    save_screenshots: bool = True

    # Mock capture settings (for testing)
    mock_capture_source: Path | None = None  # Video file or image directory

    def __post_init__(self) -> None:
        """Ensure output directory exists."""
        if isinstance(self.output_dir, str):
            self.output_dir = Path(self.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_env(cls) -> "Config":
        """Create config from environment variables."""
        import os

        return cls(
            capture_fps=int(os.getenv("CAPTURE_FPS", "30")),
            hash_threshold=int(os.getenv("HASH_THRESHOLD", "15")),
            min_reel_duration=float(os.getenv("MIN_REEL_DURATION", "0.5")),
            printer_type=os.getenv("PRINTER_TYPE", "mock"),  # type: ignore
            printer_device=os.getenv("PRINTER_DEVICE", "/dev/usb/lp0"),
            output_dir=Path(os.getenv("OUTPUT_DIR", "output")),
        )
