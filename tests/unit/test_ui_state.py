"""Tests for UI AppState thread-safe update notifications."""

import threading

from src.ui.state import AppState


def test_notify_update_ignored_from_background_thread() -> None:
    """Callbacks should not be invoked from worker threads."""
    state = AppState()
    called = {"count": 0}

    def cb() -> None:
        called["count"] += 1

    state.add_update_callback(cb)

    def worker() -> None:
        state.notify_update()

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join(timeout=2.0)

    assert called["count"] == 0


def test_notify_update_runs_on_main_thread() -> None:
    """Callbacks should still execute on the main thread."""
    state = AppState()
    called = {"count": 0}

    def cb() -> None:
        called["count"] += 1

    state.add_update_callback(cb)
    state.notify_update()
    assert called["count"] == 1
