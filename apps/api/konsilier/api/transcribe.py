"""POST /v1/transcribe: dictated audio → text, for browsers without built-in speech recognition.

Same auth as the chat (the bearer token every visitor gets on arrival, anonymous or signed in). The audio is
passed to the free Gemini API and dropped: it is neither stored nor logged.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from ..container import Container
from ..core.models import User
from ..transcribe import MAX_AUDIO_BYTES, TranscribeFailed, TranscribeUnavailable, audio_type
from .deps import current_user, get_container

router = APIRouter(prefix="/v1")


def _client_ip(request: Request) -> str | None:
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else None)


def _err(status: int, code: str) -> HTTPException:
    return HTTPException(status, {"code": code, "message": code})


@router.post("/transcribe")
def transcribe(request: Request, file: UploadFile = File(...), lang: str = Form("ru"),
               user: User = Depends(current_user), container: Container = Depends(get_container)) -> dict[str, Any]:
    transcriber = container.transcriber
    if transcriber is None:
        raise _err(503, "transcribe_unavailable")
    mime = audio_type(file.content_type, file.filename)
    if mime is None:
        raise _err(415, "unsupported_audio")
    audio = file.file.read(MAX_AUDIO_BYTES + 1)
    if len(audio) > MAX_AUDIO_BYTES:
        raise _err(413, "audio_too_large")
    if not audio:
        raise _err(422, "empty_audio")
    # anonymous visitors can mint new tokens, so the IP address bounds them too
    per_user, per_ip = container.transcribe_limits
    ip = _client_ip(request)
    if not per_user.hit(f"u:{user.id}") or (ip and not per_ip.hit(f"ip:{container.identities.h('ip', ip)}")):
        raise _err(429, "too_many_transcriptions")
    try:
        text = transcriber.transcribe(audio, mime, (lang or "ru")[:8])
    except TranscribeUnavailable:
        raise _err(503, "transcribe_busy") from None
    except TranscribeFailed:
        raise _err(502, "transcribe_failed") from None
    return {"text": text}
