"""Tests for session replay generation."""

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from src.ui.services.replay_service import ensure_session_replay_video, get_session_replay_path


def test_ensure_session_replay_video_builds_file(tmp_path: Path) -> None:
    """Replay should be generated when receipt screenshots are available."""
    shot1 = tmp_path / "reel_0001.png"
    shot2 = tmp_path / "reel_0002.png"
    Image.new("RGB", (240, 420), color=(10, 20, 30)).save(shot1)
    Image.new("RGB", (240, 420), color=(30, 20, 10)).save(shot2)

    receipts = [
        SimpleNamespace(
            reel_number=1,
            duration_seconds=0.6,
            screenshot_path=str(shot1),
            timestamp=datetime.now(),
        ),
        SimpleNamespace(
            reel_number=2,
            duration_seconds=0.7,
            screenshot_path=str(shot2),
            timestamp=datetime.now(),
        ),
    ]
    session = SimpleNamespace(
        start_time=datetime.now(),
        total_reels=2,
        total_time_seconds=1.3,
    )

    with patch("src.ui.services.replay_service.REPLAY_DIR", tmp_path / "replays"), \
         patch("src.ui.services.replay_service.SessionRepository.get_session", return_value=session), \
         patch("src.ui.services.replay_service.SessionRepository.get_session_receipts", return_value=receipts):
        replay = ensure_session_replay_video(123)

    assert replay is not None
    assert Path(replay).exists()
    assert Path(replay).suffix == ".mp4"


def test_get_session_replay_path_stable_name(tmp_path: Path) -> None:
    """Replay path should be deterministic from session id."""
    with patch("src.ui.services.replay_service.REPLAY_DIR", tmp_path):
        path = get_session_replay_path(77)
    assert path.name == "session_77.mp4"


def test_existing_replay_is_normalized_before_return(tmp_path: Path) -> None:
    """Existing replay should pass through browser-compat normalization flow."""
    replay_path = tmp_path / "session_88.mp4"
    replay_path.write_bytes(b"x" * 4096)

    with patch("src.ui.services.replay_service.REPLAY_DIR", tmp_path), \
         patch("src.ui.services.replay_service._is_replay_current", return_value=True), \
         patch("src.ui.services.replay_service._normalize_existing_replay_for_browser") as normalize:
        replay = ensure_session_replay_video(88)

    assert replay == str(replay_path.resolve())
    normalize.assert_called_once_with(replay_path)
