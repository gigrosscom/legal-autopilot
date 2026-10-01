"""The chat's Markdown → WhatsApp formatting, and long texts cut into messages.

WhatsApp knows *bold*, _italic_, ~strikethrough~ and ```monospace```; no headings, no links with a title. Each message
is billed (service messages, see team/integrations/whatsapp.md), so a text is cut only when it is over the limit.
"""

from __future__ import annotations

import re

from .graph import TEXT_MAX

MORE = re.compile(r"\s*\[\[\s*MORE\s*\]\]\s*")
BOLD = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*|__(?=\S)(.+?)(?<=\S)__")
ITALIC = re.compile(r"(?<![\w*])\*(?=\S)([^*\n]+?)(?<=\S)\*(?![\w*])")
STRIKE = re.compile(r"~~(?=\S)(.+?)(?<=\S)~~")
HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", re.MULTILINE)
LINK = re.compile(r"\[([^\]\n]+)\]\((https?://[^)\s]+)\)")
BULLET = re.compile(r"^(\s*)[-*+]\s+", re.MULTILINE)
RULE = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$", re.MULTILINE)

_B = "\x00"  # stands for a bold marker while single asterisks become italics


def to_whatsapp(md: str) -> str:
    text = MORE.sub("\n\n", md or "")  # the site's «Подробнее» cut: here the details simply follow
    text = RULE.sub("", text)
    text = LINK.sub(lambda m: m.group(1) if m.group(1) == m.group(2) else f"{m.group(1)} ({m.group(2)})", text)
    text = HEADING.sub(lambda m: f"{_B}{m.group(1).strip('*_ ')}{_B}", text)
    text = BOLD.sub(lambda m: f"{_B}{m.group(1) or m.group(2)}{_B}", text)
    text = BULLET.sub(lambda m: f"{m.group(1)}• ", text)
    text = ITALIC.sub(r"_\1_", text)
    text = STRIKE.sub(r"~\1~", text)
    text = text.replace(_B, "*")
    text = re.sub(r"[ \t]+\n", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def split(text: str, limit: int = TEXT_MAX) -> list[str]:
    """Cut at paragraph, then line, then word boundaries; never more pieces than needed."""
    text = text.strip()
    parts: list[str] = []
    while len(text) > limit:
        cut = -1
        for sep in ("\n\n", "\n", " "):
            cut = text.rfind(sep, 0, limit + 1)
            if cut > limit // 3:
                break
        if cut <= 0:
            cut = limit
        parts.append(text[:cut].rstrip())
        text = text[cut:].lstrip()
    if text:
        parts.append(text)
    return parts
