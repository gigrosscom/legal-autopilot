"""Voice input: POST /v1/transcribe on the free Gemini API (faked here, no network)."""

from __future__ import annotations

import base64
import json

import httpx

from konsilier.transcribe import (GeminiTranscriber, SlidingLimiter, TranscribeFailed, TranscribeUnavailable,
                                  audio_type)


class FakeTranscriber:
    def __init__(self, text="Сосед затопил квартиру", exc=None):
        self.text, self.exc, self.calls = text, exc, []

    def transcribe(self, audio, mime, lang):
        self.calls.append((audio, mime, lang))
        if self.exc:
            raise self.exc
        return self.text


def _token(client) -> str:
    return client.post("/v1/users", json={"language": "ru"}).json()["token"]


def _post(client, token, data=b"\x1aE\xdf\xa3webm", ctype="audio/webm;codecs=opus", name="voice.webm", lang="ru",
          headers=None):
    h = {"Authorization": f"Bearer {token}"} if token else {}
    return client.post("/v1/transcribe", files={"file": (name, data, ctype)}, data={"lang": lang},
                       headers={**h, **(headers or {})})


def test_transcribes_audio_with_its_type_and_language(ctx):
    fake = FakeTranscriber()
    ctx.container.transcriber = fake
    r = _post(ctx.client, _token(ctx.client), lang="kk")
    assert r.status_code == 200, r.text
    assert r.json() == {"text": "Сосед затопил квартиру"}
    assert fake.calls == [(b"\x1aE\xdf\xa3webm", "audio/webm", "kk")]
    # Safari records audio/mp4; m4a by extension when the type is generic
    assert _post(ctx.client, _token(ctx.client), ctype="audio/mp4").status_code == 200
    assert _post(ctx.client, _token(ctx.client), ctype="application/octet-stream", name="a.m4a").status_code == 200
    assert fake.calls[-1][1] == "audio/mp4"


def test_needs_the_chat_token(ctx):
    ctx.container.transcriber = FakeTranscriber()
    assert _post(ctx.client, None).status_code == 401


def test_503_when_gemini_is_not_configured(ctx):
    ctx.container.transcriber = None  # what build_container leaves without GEMINI_API_KEY
    r = _post(ctx.client, _token(ctx.client))
    assert r.status_code == 503
    assert r.json()["detail"]["code"] == "transcribe_unavailable"


def test_rejects_other_files_and_oversized_audio(ctx):
    ctx.container.transcriber = fake = FakeTranscriber()
    token = _token(ctx.client)
    assert _post(ctx.client, token, ctype="application/pdf", name="x.pdf").json()["detail"]["code"] == "unsupported_audio"
    r = _post(ctx.client, token, data=b"0" * (10 * 1024 * 1024 + 1))
    assert r.status_code == 413 and r.json()["detail"]["code"] == "audio_too_large"
    assert _post(ctx.client, token, data=b"").status_code == 422
    assert fake.calls == []


def test_busy_and_failed_gemini(ctx):
    token = _token(ctx.client)
    ctx.container.transcriber = FakeTranscriber(exc=TranscribeUnavailable("429"))
    r = _post(ctx.client, token)
    assert r.status_code == 503 and r.json()["detail"]["code"] == "transcribe_busy"
    ctx.container.transcriber = FakeTranscriber(exc=TranscribeFailed("400"))
    assert _post(ctx.client, token).json()["detail"]["code"] == "transcribe_failed"


def test_rate_limited_per_account_and_per_ip(ctx):
    ctx.container.transcriber = FakeTranscriber()
    ctx.container.transcribe_limits = (SlidingLimiter(2), SlidingLimiter(3))
    a = _token(ctx.client)
    assert [_post(ctx.client, a).status_code for _ in range(3)] == [200, 200, 429]
    assert _post(ctx.client, a).json()["detail"]["code"] == "too_many_transcriptions"
    # a fresh anonymous token from the same address is still bounded by the IP limit
    b = _token(ctx.client)
    assert [_post(ctx.client, b).status_code for _ in range(2)] == [200, 429]
    # another address is not
    assert _post(ctx.client, _token(ctx.client), headers={"X-Forwarded-For": "10.0.0.9"}).status_code == 200


def test_limiter_window_slides():
    lim = SlidingLimiter(1, window=60)
    assert lim.hit("k", now=0) and not lim.hit("k", now=30) and lim.hit("k", now=61)


def test_audio_types():
    assert audio_type("audio/webm;codecs=opus", "x") == "audio/webm"
    assert audio_type("audio/ogg; codecs=opus", None) == "audio/ogg"
    assert audio_type("audio/x-m4a", None) == "audio/mp4"
    assert audio_type("audio/x-wav", None) == "audio/wav"
    assert audio_type("", "rec.wav") == "audio/wav"
    assert audio_type("image/png", "a.png") is None


def _gemini(handler) -> tuple[GeminiTranscriber, list]:
    seen: list = []

    def h(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return handler(req)

    return GeminiTranscriber("key", ("m1", "m2", "m1"), http=httpx.Client(transport=httpx.MockTransport(h))), seen


def test_gemini_request_sends_audio_inline_and_reads_text():
    t, seen = _gemini(lambda req: httpx.Response(200, json={"candidates": [{"content": {"parts": [
        {"text": "thinking", "thought": True}, {"text": " Hello "}, {"text": "world."}]}}]}))
    assert t.transcribe(b"abc", "audio/webm", "en") == "Hello world."
    req = seen[0]
    assert req.url.path.endswith("/models/m1:generateContent") and req.headers["x-goog-api-key"] == "key"
    parts = json.loads(req.content)["contents"][0]["parts"]
    assert parts[0]["inlineData"] == {"mimeType": "audio/webm", "data": base64.b64encode(b"abc").decode()}
    assert "verbatim" in parts[1]["text"] and "English" in parts[1]["text"] and "no commentary" in parts[1]["text"]


def test_gemini_next_model_on_quota_then_unavailable():
    calls = iter([429, 200])
    t, seen = _gemini(lambda req: httpx.Response(s := next(calls), json={"candidates": [
        {"content": {"parts": [{"text": "ok"}]}}]} if s == 200 else {"error": "quota"}))
    assert t.transcribe(b"a", "audio/ogg", "ru") == "ok"
    assert [r.url.path.rsplit("/", 1)[-1] for r in seen] == ["m1:generateContent", "m2:generateContent"]

    t, seen = _gemini(lambda req: httpx.Response(503, json={}))
    try:
        t.transcribe(b"a", "audio/ogg", "ru")
        raise AssertionError("expected TranscribeUnavailable")
    except TranscribeUnavailable:
        pass
    assert len(seen) == 2  # duplicates in the model list are tried once

    t, _ = _gemini(lambda req: httpx.Response(400, json={"error": "bad audio"}))
    try:
        t.transcribe(b"a", "audio/ogg", "ru")
        raise AssertionError("expected TranscribeFailed")
    except TranscribeFailed:
        pass


# ---- live text while speaking (owner 01.10, iPhone app): partial=1 ---------------------------------------------
def _partial(client, token, **kw):
    return client.post("/v1/transcribe", files={"file": ("voice.m4a", b"\x00\x00ftypM4A", "audio/mp4")},
                       data={"lang": "kk", "partial": "true"}, headers={"Authorization": f"Bearer {token}"}, **kw)


def test_partial_goes_to_the_fast_transcriber_with_its_own_limits(ctx):
    final, fast = FakeTranscriber("финал"), FakeTranscriber("Сатушы ақшаны")
    ctx.container.transcriber, ctx.container.partial_transcriber = final, fast
    ctx.container.transcribe_limits = (SlidingLimiter(1), SlidingLimiter(1))
    ctx.container.partial_limits = (SlidingLimiter(5), SlidingLimiter(5))
    tok = _token(ctx.client)
    assert [_partial(ctx.client, tok).json()["text"] for _ in range(3)] == ["Сатушы ақшаны"] * 3
    assert fast.calls[0][1:] == ("audio/mp4", "kk") and final.calls == []
    # the live text does not use up the final transcriptions, and the final one still goes to Gemini
    assert _post(ctx.client, tok).json() == {"text": "финал"}
    assert [_partial(ctx.client, tok).status_code for _ in range(3)] == [200, 200, 429]


def test_partial_without_groq_uses_the_same_transcriber(ctx):
    ctx.container.transcriber, ctx.container.partial_transcriber = FakeTranscriber("жарайды"), None
    assert _partial(ctx.client, _token(ctx.client)).json() == {"text": "жарайды"}


def test_groq_whisper_request():
    from konsilier.transcribe import GroqWhisperTranscriber

    seen = []

    def handler(req):
        seen.append(req)
        return httpx.Response(200, json={"text": " Купил телевизор "})
    t = GroqWhisperTranscriber("gk", http=httpx.Client(transport=httpx.MockTransport(handler)))
    assert t.transcribe(b"abc", "audio/mp4", "kk") == "Купил телевизор"
    req = seen[0]
    assert req.url.path.endswith("/audio/transcriptions") and req.headers["authorization"] == "Bearer gk"
    body = req.content.decode("latin-1")
    assert 'name="language"' in body and "kk" in body and "whisper-large-v3-turbo" in body and 'filename="voice.m4a"' in body
    busy = GroqWhisperTranscriber("gk", http=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(429))))
    try:
        busy.transcribe(b"a", "audio/webm", "ru")
        raise AssertionError("expected TranscribeUnavailable")
    except TranscribeUnavailable:
        pass
