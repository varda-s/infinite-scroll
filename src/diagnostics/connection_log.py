"""Connection diagnostics log helpers for uxplay pairing flow."""

from datetime import datetime
from pathlib import Path


CONNECTION_LOG_PATH = Path("output/uxplay.connection.log")


def log_connection_event(event: str, detail: str = "") -> None:
    """Append a timestamped connection event to the diagnostics log."""
    try:
        CONNECTION_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"{timestamp} | {event}"
        if detail:
            line = f"{line} | {detail}"
        with CONNECTION_LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(f"{line}\n")
    except Exception:
        # Diagnostics must never interrupt pairing flow.
        pass

