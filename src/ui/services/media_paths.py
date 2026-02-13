"""Helpers for serving local media files via NiceGUI static routes."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
OUTPUT_ROOT = (PROJECT_ROOT / "output").resolve()
MEDIA_ROUTE = "/output"


def to_media_url(path: str | None) -> str | None:
    """Map a local filesystem path under output/ to a browser URL.

    Returns None when path is missing, doesn't exist, or is outside output root.
    """
    if not path:
        return None

    p = Path(path)
    if not p.is_absolute():
        p = (Path.cwd() / p).resolve()
    else:
        p = p.resolve()

    if not p.exists():
        return None

    try:
        rel = p.relative_to(OUTPUT_ROOT)
    except ValueError:
        return None

    return f"{MEDIA_ROUTE}/{rel.as_posix()}"
