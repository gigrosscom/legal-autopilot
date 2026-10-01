"""Human texts for API errors, shared by the Telegram and WhatsApp bots."""

from __future__ import annotations

import httpx

from .api import ApiError
from .i18n import t

# API error codes the client may meet; each has a short text in locales/*.yaml → errors.<code>
ERROR_CODES = ("too_many_messages", "too_many_questions", "too_many", "busy", "agent_failed", "agent_unavailable",
               "payment_required", "payment_unavailable", "awaiting_approval", "invalid_transition", "contact_required",
               "submission_failed")


def error_text(exc: BaseException, lang: str, prefix: str = "") -> str:
    """A short human message for the user; the code itself goes only to the log. ``prefix`` ("whatsapp."): a
    channel's own wording of a text, where it has one."""
    def text(key: str) -> str:
        own = t(prefix + key, lang) if prefix else prefix + key
        return own if own != prefix + key else t(key, lang)

    if isinstance(exc, ApiError):
        code = exc.detail.get("code") if isinstance(exc.detail, dict) else None
        if code in ERROR_CODES:
            return text(f"errors.{code}")
        if exc.status == 429:
            return text("errors.too_many")
        if exc.status >= 500:
            return text("errors.unavailable")
    elif isinstance(exc, httpx.HTTPError):  # API unreachable or timed out
        return text("errors.unavailable")
    return text("error")
