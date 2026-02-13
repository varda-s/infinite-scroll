"""Tests for image utilities."""

import pytest
from PIL import Image

from src.detection.image_utils import (
    compute_phash,
    compute_dhash,
    compare_images,
    images_are_different,
    extract_center_region,
    get_dominant_colors,
    is_mostly_black,
    calculate_image_entropy,
)


class TestPerceptualHashing:
    """Tests for perceptual hashing functions."""

    def test_compute_phash_returns_hash(self, sample_image: Image.Image) -> None:
        """Test that compute_phash returns a hash object."""
        hash_val = compute_phash(sample_image)
        assert hash_val is not None
        assert len(str(hash_val)) > 0

    def test_compute_dhash_returns_hash(self, sample_image: Image.Image) -> None:
        """Test that compute_dhash returns a hash object."""
        hash_val = compute_dhash(sample_image)
        assert hash_val is not None
        assert len(str(hash_val)) > 0

    def test_same_image_same_hash(self, sample_image: Image.Image) -> None:
        """Test that the same image produces the same hash."""
        hash1 = compute_phash(sample_image)
        hash2 = compute_phash(sample_image)
        assert hash1 == hash2

    def test_different_images_different_hash(
        self, sample_image: Image.Image, sample_image_2: Image.Image
    ) -> None:
        """Test that different images produce different hashes."""
        hash1 = compute_phash(sample_image)
        hash2 = compute_phash(sample_image_2)
        # Different images should have different hashes
        difference = hash1 - hash2
        assert difference > 0


class TestImageComparison:
    """Tests for image comparison functions."""

    def test_compare_same_images_zero_difference(self, sample_image: Image.Image) -> None:
        """Test that comparing same image returns 0 difference."""
        difference = compare_images(sample_image, sample_image)
        assert difference == 0

    def test_compare_different_images_positive_difference(
        self, sample_image: Image.Image, sample_image_2: Image.Image
    ) -> None:
        """Test that comparing different images returns positive difference."""
        difference = compare_images(sample_image, sample_image_2)
        assert difference > 0

    def test_images_are_different_same_image(self, sample_image: Image.Image) -> None:
        """Test that same image is not considered different."""
        result = images_are_different(sample_image, sample_image)
        assert result == False

    def test_images_are_different_different_images(
        self, sample_image: Image.Image, sample_image_2: Image.Image
    ) -> None:
        """Test that different images are considered different."""
        result = images_are_different(sample_image, sample_image_2, threshold=5)
        assert result == True

    def test_identical_images_zero_difference(self, sample_image: Image.Image) -> None:
        """Test that identical images have zero difference."""
        # Make a copy to ensure we're testing with a different object
        copy = sample_image.copy()
        difference = compare_images(sample_image, copy)
        assert difference == 0


class TestImageProcessing:
    """Tests for image processing utilities."""

    def test_extract_center_region(self, sample_image: Image.Image) -> None:
        """Test center region extraction."""
        center = extract_center_region(sample_image, width_ratio=0.5, height_ratio=0.5)

        # Center should be smaller
        assert center.width < sample_image.width
        assert center.height < sample_image.height

        # Should be approximately half size
        assert center.width == pytest.approx(sample_image.width * 0.5, rel=0.1)
        assert center.height == pytest.approx(sample_image.height * 0.5, rel=0.1)

    def test_get_dominant_colors(self, sample_image: Image.Image) -> None:
        """Test dominant color extraction."""
        colors = get_dominant_colors(sample_image, n_colors=3)

        assert len(colors) == 3
        for color in colors:
            assert len(color) == 3  # RGB
            assert all(0 <= c <= 255 for c in color)

    def test_is_mostly_black_with_black_image(self, black_image: Image.Image) -> None:
        """Test black image detection."""
        result = is_mostly_black(black_image)
        assert result == True

    def test_is_mostly_black_with_colored_image(self, sample_image: Image.Image) -> None:
        """Test that colored image is not detected as mostly black."""
        result = is_mostly_black(sample_image)
        assert result == False

    def test_calculate_image_entropy_black_image(self, black_image: Image.Image) -> None:
        """Test entropy calculation for simple image."""
        entropy = calculate_image_entropy(black_image)
        # Solid black image should have 0 entropy
        assert entropy == 0.0

    def test_calculate_image_entropy_complex_image(self, sample_image: Image.Image) -> None:
        """Test entropy calculation for complex image."""
        entropy = calculate_image_entropy(sample_image)
        # Complex image should have positive entropy
        assert entropy > 0
