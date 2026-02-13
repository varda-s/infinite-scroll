"""Parallel Gemini categorization for reel screenshots."""

from __future__ import annotations

import io
import os
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
import re

from PIL import Image

from src.printing.legacy_format import placeholder_topic

MODEL_PREFERENCE = [
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.0-flash-lite",
    "gemini-2.0-flash",
]


class GeminiCategorizer:
    """Classify reel screenshots in parallel using Gemini."""

    def __init__(self, max_workers: int = 4) -> None:
        self._lock = threading.Lock()
        self._thread_local = threading.local()
        self._futures: dict[int, Future[str]] = {}
        self._results: dict[int, str] = {}

        self._api_key = self._load_api_key()
        self._model_name = self._resolve_model_name()
        self._enabled = bool(self._api_key and self._model_name)
        self._executor: ThreadPoolExecutor | None = (
            ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="gemini-reel")
            if self._enabled
            else None
        )

    def submit(self, reel_number: int, screenshot: Image.Image) -> None:
        """Submit screenshot categorization request."""
        if self._executor is None:
            print(
                f"[Gemini] Reel {reel_number}: categorizer disabled, using placeholder topic."
            )
            with self._lock:
                self._results[reel_number] = placeholder_topic(reel_number)
            return

        image_copy = screenshot.copy()
        print(f"[Gemini] Reel {reel_number}: queued categorization request.")
        future = self._executor.submit(self._classify_safe, reel_number, image_copy)
        with self._lock:
            self._futures[reel_number] = future

    def wait_for_all(self) -> dict[int, str]:
        """Block until all in-flight categorization calls finish."""
        with self._lock:
            pending = dict(self._futures)
        if pending:
            print(f"[Gemini] Waiting for {len(pending)} in-flight categorization calls...")

        for reel_number, future in pending.items():
            topic = future.result()
            with self._lock:
                self._results[reel_number] = topic
            print(f"[Gemini] Reel {reel_number}: final category='{topic}'")

        return self.results()

    def results(self) -> dict[int, str]:
        """Return completed categorization results."""
        with self._lock:
            return dict(self._results)

    def close(self) -> None:
        """Shutdown executor."""
        if self._executor is not None:
            self._executor.shutdown(wait=False)
            self._executor = None

    def _classify_safe(self, reel_number: int, screenshot: Image.Image) -> str:
        try:
            return self._classify(reel_number, screenshot)
        except Exception as e:
            print(f"[Gemini] Reel {reel_number}: request failed ({e}), using placeholder.")
            return placeholder_topic(reel_number)

    def _classify(self, reel_number: int, screenshot: Image.Image) -> str:
        client = self._get_thread_client()
        if client is None or not self._model_name:
            return placeholder_topic(reel_number)

        from google.genai import types as genai_types  # type: ignore

        buffer = io.BytesIO()
        screenshot.save(buffer, format="JPEG", quality=90)
        image_bytes = buffer.getvalue()

        prompt = (
            "Return ONLY one concise main category/topic for this social media reel screenshot. "
            "Examples: Cooking Tutorial, Tech Review, Comedy Skit, Travel Vlog, Fashion Ad, "
            "Sports Highlight, Food Review."
        )
        started_at = time.time()
        print(
            f"[Gemini] Reel {reel_number}: calling model='{self._model_name}' "
            f"(image_bytes={len(image_bytes)})."
        )

        response = client.models.generate_content(
            model=self._model_name,
            contents=[
                genai_types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                prompt,
            ],
        )
        elapsed_ms = (time.time() - started_at) * 1000.0
        raw_text = (getattr(response, "text", "") or "").strip()
        print(
            f"[Gemini] Reel {reel_number}: response in {elapsed_ms:.0f}ms, "
            f"raw_text={raw_text!r}"
        )
        topic = raw_text
        if not topic:
            return placeholder_topic(reel_number)
        # Keep category short enough for receipt width.
        topic = " ".join(topic.split())
        topic = re.sub(r"[\[\]\$\n\r\t]", "", topic)
        topic = topic.strip(" .-")
        return topic[:22] or placeholder_topic(reel_number)

    def _get_thread_client(self):
        if not self._api_key:
            return None
        existing = getattr(self._thread_local, "client", None)
        if existing is not None:
            return existing
        try:
            from google import genai  # type: ignore

            client = genai.Client(api_key=self._api_key)
        except Exception:
            return None
        self._thread_local.client = client
        return client

    def _resolve_model_name(self) -> str | None:
        explicit = os.getenv("GEMINI_MODEL_NAME", "").strip()
        if explicit:
            return explicit

        client = self._bootstrap_client()
        if client is None:
            return None

        try:
            model_map: dict[str, str] = {}
            for model in client.models.list():
                name = getattr(model, "name", "") or ""
                if not name:
                    continue
                normalized = name.removeprefix("models/")
                model_map[normalized] = name

            for preferred in MODEL_PREFERENCE:
                if preferred in model_map:
                    return model_map[preferred]
        except Exception:
            pass

        return MODEL_PREFERENCE[0]

    def _bootstrap_client(self):
        if not self._api_key:
            return None
        try:
            from google import genai  # type: ignore

            return genai.Client(api_key=self._api_key)
        except Exception:
            return None

    @staticmethod
    def _load_api_key() -> str:
        if os.getenv("PYTEST_CURRENT_TEST"):
            return ""

        env_key = os.getenv("GEMINI_API_KEY", "").strip() or os.getenv("GOOGLE_API_KEY", "").strip()
        if env_key:
            return env_key

        # Lightweight .env reader so this works without extra dependencies.
        env_path = Path(__file__).resolve().parents[2] / ".env"
        if not env_path.exists():
            return ""

        try:
            for raw_line in env_path.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key in {"GEMINI_API_KEY", "GOOGLE_API_KEY"} and value:
                    return value
        except Exception:
            return ""
        return ""
