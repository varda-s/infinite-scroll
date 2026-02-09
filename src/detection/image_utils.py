"""Image processing utilities for reel detection."""

import imagehash
import numpy as np
from PIL import Image


def compute_phash(image: Image.Image, hash_size: int = 16) -> imagehash.ImageHash:
    """Compute perceptual hash of an image.

    Args:
        image: PIL Image to hash.
        hash_size: Size of the hash (default 16 for 256-bit hash).

    Returns:
        ImageHash object that can be compared with other hashes.
    """
    return imagehash.phash(image, hash_size=hash_size)


def compute_dhash(image: Image.Image, hash_size: int = 16) -> imagehash.ImageHash:
    """Compute difference hash of an image.

    Difference hash is good at detecting shifts/scrolls.

    Args:
        image: PIL Image to hash.
        hash_size: Size of the hash.

    Returns:
        ImageHash object.
    """
    return imagehash.dhash(image, hash_size=hash_size)


def compare_images(
    image1: Image.Image,
    image2: Image.Image,
    hash_size: int = 16,
) -> int:
    """Compare two images and return their hash difference.

    Args:
        image1: First image.
        image2: Second image.
        hash_size: Size of hash to use.

    Returns:
        Hamming distance between the two image hashes.
        Lower values mean more similar images.
    """
    hash1 = compute_phash(image1, hash_size)
    hash2 = compute_phash(image2, hash_size)
    return hash1 - hash2


def images_are_different(
    image1: Image.Image,
    image2: Image.Image,
    threshold: int = 15,
    hash_size: int = 16,
) -> bool:
    """Check if two images are significantly different.

    Args:
        image1: First image.
        image2: Second image.
        threshold: Maximum hash difference to consider images as same.
        hash_size: Size of hash to use.

    Returns:
        True if images are different enough to be considered a new reel.
    """
    difference = compare_images(image1, image2, hash_size)
    return difference > threshold


def extract_center_region(
    image: Image.Image,
    width_ratio: float = 0.8,
    height_ratio: float = 0.6,
) -> Image.Image:
    """Extract the center region of an image.

    This helps focus on content and ignore UI elements at edges.

    Args:
        image: Original image.
        width_ratio: Ratio of width to keep (centered).
        height_ratio: Ratio of height to keep (centered).

    Returns:
        Cropped center region.
    """
    width, height = image.size

    left = int(width * (1 - width_ratio) / 2)
    right = int(width * (1 + width_ratio) / 2)
    top = int(height * (1 - height_ratio) / 2)
    bottom = int(height * (1 + height_ratio) / 2)

    return image.crop((left, top, right, bottom))


def get_dominant_colors(
    image: Image.Image,
    n_colors: int = 5,
) -> list[tuple[int, int, int]]:
    """Get dominant colors in an image.

    Useful for detecting UI elements or content type.

    Args:
        image: Image to analyze.
        n_colors: Number of dominant colors to return.

    Returns:
        List of RGB tuples representing dominant colors.
    """
    # Resize for faster processing
    image = image.resize((100, 100))
    image = image.convert("RGB")

    # Get pixel data
    pixels = list(image.getdata())

    # Simple histogram-based approach
    from collections import Counter

    # Quantize colors to reduce noise
    quantized = [(r // 32 * 32, g // 32 * 32, b // 32 * 32) for r, g, b in pixels]
    color_counts = Counter(quantized)

    return [color for color, _ in color_counts.most_common(n_colors)]


def is_mostly_black(image: Image.Image, threshold: float = 0.7) -> bool:
    """Check if image is mostly black (loading screen or transition).

    Args:
        image: Image to check.
        threshold: Minimum ratio of dark pixels to be considered "mostly black".

    Returns:
        True if image is mostly black.
    """
    grayscale = image.convert("L")
    pixels = np.array(grayscale)
    dark_pixels = np.sum(pixels < 30)
    total_pixels = pixels.size
    return (dark_pixels / total_pixels) > threshold


def calculate_image_entropy(image: Image.Image) -> float:
    """Calculate the entropy (information content) of an image.

    Low entropy suggests a simple image (solid color, loading screen).
    High entropy suggests complex content.

    Args:
        image: Image to analyze.

    Returns:
        Entropy value (higher = more complex).
    """
    grayscale = image.convert("L")
    histogram = grayscale.histogram()

    # Normalize histogram
    total = sum(histogram)
    probabilities = [h / total for h in histogram if h > 0]

    # Calculate entropy
    entropy = -sum(p * np.log2(p) for p in probabilities)
    return entropy
