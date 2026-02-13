"""Tests for UI media path helpers."""

from pathlib import Path

from src.ui.services import media_paths


def test_to_media_url_maps_output_file(tmp_path: Path, monkeypatch) -> None:
    """Files under output root should be converted to browser URLs."""
    output_root = tmp_path / "output"
    image_path = output_root / "sessions" / "session_1" / "reel_0001.png"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(b"png")

    monkeypatch.setattr(media_paths, "OUTPUT_ROOT", output_root.resolve())

    url = media_paths.to_media_url(str(image_path))
    assert url == "/output/sessions/session_1/reel_0001.png"


def test_to_media_url_rejects_non_output_file(tmp_path: Path, monkeypatch) -> None:
    """Files outside output root should not be exposed as URLs."""
    output_root = tmp_path / "output"
    other_path = tmp_path / "secret" / "file.png"
    other_path.parent.mkdir(parents=True, exist_ok=True)
    other_path.write_bytes(b"x")

    monkeypatch.setattr(media_paths, "OUTPUT_ROOT", output_root.resolve())

    assert media_paths.to_media_url(str(other_path)) is None

