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

MODEL_PREFERENCE = [
    "models/gemini-2.5-flash-lite",
    "models/gemini-2.5-flash",
    "models/gemini-2.0-flash-lite",
    "models/gemini-2.0-flash",
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
        self._sdk_available = self._check_sdk_available()
        self._enabled = bool(self._api_key and self._model_name and self._sdk_available)
        self._executor: ThreadPoolExecutor | None = (
            ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="gemini-reel")
            if self._enabled
            else None
        )

    def submit(
        self,
        reel_number: int,
        screenshot: Image.Image,
        analysis_frames: list[Image.Image] | None = None,
    ) -> None:
        """Submit screenshot categorization request."""
        if self._executor is None:
            reason = []
            if not self._api_key:
                reason.append("missing API key")
            if not self._model_name:
                reason.append("missing model")
            if not self._sdk_available:
                reason.append("google-genai not installed")
            why = ", ".join(reason) if reason else "unknown reason"
            print(f"[Gemini] Reel {reel_number}: categorizer disabled ({why}), using fallback topic.")
            with self._lock:
                self._results[reel_number] = "Unclassified"
            return

        image_copy = screenshot.copy()
        frame_copies = [frame.copy() for frame in (analysis_frames or [])[:6]]
        print(f"[Gemini] Reel {reel_number}: queued categorization request.")
        future = self._executor.submit(self._classify_safe, reel_number, image_copy, frame_copies)
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

    def _classify_safe(
        self,
        reel_number: int,
        screenshot: Image.Image,
        analysis_frames: list[Image.Image],
    ) -> str:
        try:
            return self._classify(reel_number, screenshot, analysis_frames)
        except Exception as e:
            print(f"[Gemini] Reel {reel_number}: request failed ({e}), using fallback.")
            return "Unclassified"

    def _classify(
        self,
        reel_number: int,
        screenshot: Image.Image,
        analysis_frames: list[Image.Image],
    ) -> str:
        client = self._get_thread_client()
        if client is None or not self._model_name:
            return "Unclassified"

        from google.genai import types as genai_types  # type: ignore

        frames = self._prepare_analysis_frames(screenshot, analysis_frames)
        parts = []
        total_bytes = 0
        for frame in frames:
            buffer = io.BytesIO()
            frame.save(buffer, format="JPEG", quality=88)
            image_bytes = buffer.getvalue()
            total_bytes += len(image_bytes)
            parts.append(genai_types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"))

        prompt = (
            "You are classifying one Instagram reel from several sampled frames taken across the same clip. "
            "Infer the most specific subject or content type visible across the frames. "
            "Return ONLY one short label, 2 to 5 words. "
            "Prefer concrete topics like 'Street Interview', 'Sneaker Ad', 'Makeup Tutorial', "
            "'Stand-up Comedy', 'Gaming Clip', 'Recipe Demo', 'Workout Advice'. "
            "Do NOT return generic labels like 'Content', 'Entertainment', 'Video', 'Social Media', "
            "'Lifestyle', 'Miscellaneous', or 'Advertisement' unless the frames truly reveal nothing else."
        )
        started_at = time.time()
        print(
            f"[Gemini] Reel {reel_number}: calling model='{self._model_name}' "
            f"(frames={len(frames)} bytes={total_bytes})."
        )

        response = client.models.generate_content(
            model=self._model_name,
            contents=[*parts, prompt],
        )
        elapsed_ms = (time.time() - started_at) * 1000.0
        raw_text = (getattr(response, "text", "") or "").strip()
        print(
            f"[Gemini] Reel {reel_number}: response in {elapsed_ms:.0f}ms, "
            f"raw_text={raw_text!r}"
        )
        topic = raw_text
        if not topic:
            return "Unclassified"
        # Keep category short enough for receipt width.
        topic = " ".join(topic.split())
        topic = re.sub(r"^topic\s*:\s*", "", topic, flags=re.IGNORECASE)
        topic = re.sub(r"[\[\]\$\n\r\t]", "", topic)
        topic = topic.strip(" .-")
        topic = re.sub(r"^(category|label)\s*:\s*", "", topic, flags=re.IGNORECASE)
        if topic.lower() in {"content", "video", "entertainment", "social media", "miscellaneous"}:
            return "Unclassified"
        return topic[:22] or "Unclassified"

    def _prepare_analysis_frames(
        self,
        screenshot: Image.Image,
        analysis_frames: list[Image.Image],
    ) -> list[Image.Image]:
        """Return a small diverse set of frames for Gemini classification."""
        frames = analysis_frames[:] if analysis_frames else [screenshot]
        if not frames:
            frames = [screenshot]

        selected: list[Image.Image] = []
        if frames:
            selected.append(frames[0])
        if len(frames) >= 3:
            selected.append(frames[len(frames) // 2])
        if len(frames) >= 2:
            selected.append(frames[-1])

        # Deduplicate object identities while keeping order.
        deduped: list[Image.Image] = []
        seen_ids: set[int] = set()
        for frame in selected:
            marker = id(frame)
            if marker in seen_ids:
                continue
            seen_ids.add(marker)
            deduped.append(self._normalize_frame(frame))
        return deduped[:3] or [self._normalize_frame(screenshot)]

    def _normalize_frame(self, frame: Image.Image) -> Image.Image:
        """Resize and normalize frames for Gemini requests."""
        image = frame.convert("RGB")
        max_width = 720
        if image.width <= max_width:
            return image
        scale = max_width / float(image.width)
        new_size = (max_width, max(1, int(image.height * scale)))
        return image.resize(new_size, Image.Resampling.LANCZOS)

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
        if self._api_key:
            return MODEL_PREFERENCE[0]
        return None

    def _bootstrap_client(self):
        if not self._api_key:
            return None
        try:
            from google import genai  # type: ignore

            return genai.Client(api_key=self._api_key)
        except Exception:
            return None

    @staticmethod
    def _check_sdk_available() -> bool:
        try:
            from google import genai  # type: ignore  # noqa: F401
            return True
        except Exception:
            return False

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
