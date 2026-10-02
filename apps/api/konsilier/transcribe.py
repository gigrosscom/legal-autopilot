"""Speech to text for the dictation button, on the free Gemini API (audio sent inline, never stored).

Browsers without built-in speech recognition (Firefox, iOS home-screen apps, some Android WebViews) record the
voice with MediaRecorder and upload it here. Only the free Gemini models are used: this never calls a paid model.
"""

from __future__ import annotations

import base64
import logging
import threading
import time
from collections import deque
from typing import Any

import httpx

from .gemini import BASE, RETRY_STATUSES

log = logging.getLogger(__name__)

MAX_AUDIO_BYTES = 10 * 1024 * 1024  # about two minutes of speech in any of the accepted formats

# Content types browsers send → the type Gemini is given. Codec parameters (";codecs=opus") are dropped first.
AUDIO_TYPES = {
    "audio/webm": "audio/webm", "video/webm": "audio/webm",
    "audio/ogg": "audio/ogg", "application/ogg": "audio/ogg",
    "audio/mp4": "audio/mp4", "video/mp4": "audio/mp4", "audio/m4a": "audio/mp4", "audio/x-m4a": "audio/mp4",
    "audio/aac": "audio/aac",
    "audio/wav": "audio/wav", "audio/x-wav": "audio/wav", "audio/wave": "audio/wav", "audio/vnd.wave": "audio/wav",
    "audio/mpeg": "audio/mp3", "audio/mp3": "audio/mp3",
}
EXTENSIONS = {"webm": "audio/webm", "ogg": "audio/ogg", "oga": "audio/ogg", "opus": "audio/ogg", "mp4": "audio/mp4",
              "m4a": "audio/mp4", "aac": "audio/aac", "wav": "audio/wav", "mp3": "audio/mp3"}

# Language of the interface → how the instruction names it (native names, so the model does not guess).
LANGUAGES = {"ru": "Russian (русский)", "kk": "қазақ тілі (kk)", "en": "English", "tr": "Turkish (Türkçe)",
             "ar": "Arabic (العربية)"}


def audio_type(content_type: str | None, filename: str | None) -> str | None:
    """The audio type to send to Gemini, or None when the upload is not a supported audio format."""
    base = (content_type or "").split(";")[0].strip().lower()
    if base in AUDIO_TYPES:
        return AUDIO_TYPES[base]
    ext = (filename or "").rsplit(".", 1)[-1].lower() if "." in (filename or "") else ""
    if base in ("", "application/octet-stream") and ext in EXTENSIONS:
        return EXTENSIONS[ext]
    return None


def instruction(lang: str) -> str:
    name = LANGUAGES.get(lang, lang or "the spoken language")
    return (f"Transcribe this audio verbatim in {name}, no commentary. Output only the words that were said, "
            "with punctuation. If nothing intelligible is said, output nothing.")


class TranscribeUnavailable(RuntimeError):
    """Every Gemini model is over quota or overloaded right now."""


class TranscribeFailed(RuntimeError):
    """Gemini refused the request (bad audio, blocked content, API error)."""


class GeminiTranscriber:
    """``transcribe(audio, mime, lang) -> text`` with the free Gemini models, first one that answers."""

    def __init__(self, api_key: str, models: tuple[str, ...], *, http: httpx.Client | None = None,
                 timeout: float = 60):
        self.api_key, self.models = api_key, tuple(dict.fromkeys(m for m in models if m))
        self.http = http or httpx.Client(timeout=timeout)

    def transcribe(self, audio: bytes, mime: str, lang: str) -> str:
        body: dict[str, Any] = {
            "contents": [{"role": "user", "parts": [
                {"inlineData": {"mimeType": mime, "data": base64.standard_b64encode(audio).decode()}},
                {"text": instruction(lang)}]}],
            "generationConfig": {"temperature": 0, "maxOutputTokens": 4096},
        }
        last = ""
        for model in self.models:
            try:
                r = self.http.post(f"{BASE}/models/{model}:generateContent", json=body,
                                   headers={"x-goog-api-key": self.api_key})
            except httpx.HTTPError as e:
                last = f"{e.__class__.__name__}: {e}"
                continue
            if r.status_code in RETRY_STATUSES:
                last = f"{r.status_code}: {r.text[:200]}"
                continue  # free-tier quotas are per model: the next one may answer
            if r.status_code >= 400:
                raise TranscribeFailed(f"gemini {r.status_code}: {r.text[:300]}")
            try:
                data = r.json()
            except ValueError as e:
                raise TranscribeFailed("gemini: invalid response") from e
            cand = (data.get("candidates") or [{}])[0]
            parts = (cand.get("content") or {}).get("parts") or []
            return "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
        log.warning("transcription unavailable: %s", last)
        raise TranscribeUnavailable(last or "no model configured")


class GroqWhisperTranscriber:
    """``transcribe(audio, mime, lang) -> text`` with Whisper on Groq (free tier, its own quota — the chat's Gemini
    quota is left alone). Fast enough for the live text while the person is still speaking (owner 01.10)."""

    URL = "https://api.groq.com/openai/v1/audio/transcriptions"
    FILE_EXT = {"audio/webm": "webm", "audio/ogg": "ogg", "audio/mp4": "m4a", "audio/aac": "m4a", "audio/wav": "wav",
                "audio/mp3": "mp3"}

    def __init__(self, api_key: str, model: str = "whisper-large-v3-turbo", *, http: httpx.Client | None = None,
                 timeout: float = 20):
        self.api_key, self.model = api_key, model
        self.http = http or httpx.Client(timeout=timeout)

    def transcribe(self, audio: bytes, mime: str, lang: str) -> str:
        data = {"model": self.model, "response_format": "json", "temperature": "0"}
        if lang in LANGUAGES:
            data["language"] = lang
        try:
            r = self.http.post(self.URL, headers={"Authorization": f"Bearer {self.api_key}"}, data=data,
                               files={"file": (f"voice.{self.FILE_EXT.get(mime, 'webm')}", audio, mime)})
        except httpx.HTTPError as e:
            raise TranscribeUnavailable(f"groq {e.__class__.__name__}") from e
        if r.status_code in RETRY_STATUSES:
            raise TranscribeUnavailable(f"groq {r.status_code}")
        if r.status_code >= 400:
            raise TranscribeFailed(f"groq {r.status_code}: {r.text[:300]}")
        try:
            return str(r.json().get("text") or "").strip()
        except ValueError as e:
            raise TranscribeFailed("groq: invalid response") from e


class SlidingLimiter:
    """At most ``limit`` hits per key in the last ``window`` seconds, kept in memory (per API worker)."""

    def __init__(self, limit: int, window: float = 3600):
        self.limit, self.window = limit, window
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str, now: float | None = None) -> bool:
        """Count one hit; False (and nothing counted) when the key is over its limit."""
        now = time.monotonic() if now is None else now
        with self._lock:
            q = self._hits.setdefault(key, deque())
            while q and q[0] <= now - self.window:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            if len(self._hits) > 10_000:  # forget idle keys so memory stays bounded
                for k in [k for k, v in self._hits.items() if not v or v[-1] <= now - self.window]:
                    del self._hits[k]
            return True
