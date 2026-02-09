"""Pytest fixtures for Instagram Reel Tracker tests."""

import tempfile
from pathlib import Path
from typing import Generator

import numpy as np
import pytest
from PIL import Image

from src.config import Config
from src.printing.mock_printer import MockPrinter


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for test outputs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def config(temp_dir: Path) -> Config:
    """Create a test configuration."""
    return Config(
        capture_fps=10,
        hash_threshold=15,
        min_reel_duration=0.5,
        printer_type="mock",
        output_dir=temp_dir,
    )


@pytest.fixture
def mock_printer(temp_dir: Path) -> MockPrinter:
    """Create a mock printer for testing."""
    return MockPrinter(output_dir=temp_dir, verbose=False)


@pytest.fixture
def sample_image() -> Image.Image:
    """Create a sample test image."""
    # Create a colorful test image
    arr = np.zeros((1920, 1080, 3), dtype=np.uint8)

    # Add some patterns
    arr[0:640, :, 0] = 255  # Red section
    arr[640:1280, :, 1] = 255  # Green section
    arr[1280:, :, 2] = 255  # Blue section

    return Image.fromarray(arr)


@pytest.fixture
def sample_image_2() -> Image.Image:
    """Create a second sample test image (different from first)."""
    arr = np.zeros((1920, 1080, 3), dtype=np.uint8)

    # Different pattern
    arr[:, 0:360, 0] = 255  # Red section
    arr[:, 360:720, 1] = 255  # Green section
    arr[:, 720:, 2] = 255  # Blue section

    return Image.fromarray(arr)


@pytest.fixture
def similar_image(sample_image: Image.Image) -> Image.Image:
    """Create an image similar to sample_image (minor changes)."""
    arr = np.array(sample_image)

    # Add minor noise
    noise = np.random.randint(-5, 5, arr.shape, dtype=np.int16)
    arr = np.clip(arr.astype(np.int16) + noise, 0, 255).astype(np.uint8)

    return Image.fromarray(arr)


@pytest.fixture
def black_image() -> Image.Image:
    """Create a mostly black image (loading screen simulation)."""
    arr = np.zeros((1920, 1080, 3), dtype=np.uint8)
    return Image.fromarray(arr)


@pytest.fixture
def test_images_dir(temp_dir: Path, sample_image: Image.Image, sample_image_2: Image.Image) -> Path:
    """Create a directory with test images."""
    images_dir = temp_dir / "test_images"
    images_dir.mkdir()

    # Save some test images
    for i in range(5):
        if i % 2 == 0:
            sample_image.save(images_dir / f"frame_{i:03d}.png")
        else:
            sample_image_2.save(images_dir / f"frame_{i:03d}.png")

    return images_dir
