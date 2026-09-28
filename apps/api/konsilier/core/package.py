"""Service scenarios (beta): a package of documents instead of a claim.

A service action lists its documents in ``package:`` (cover letter, motivation letter, checklist, inventory,
where-and-how-to-file). Everything in them is scenario data; this module only picks the lines that apply to the
person (``if`` / ``unless`` an intake field was answered) and fills in ``{placeholders}``.
Nothing here decides requirements, fees or deadlines — those come from the scenario YAML with their sources.
"""

from __future__ import annotations

from typing import Any

from .scenario import ActionSpec, Scenario
from .scenario.schema import PackageLine, PackageSection

# Fixed words of the package template, per language (the pack default is used for anything missing).
LABELS: dict[str, dict[str, str]] = {
    "ru": {"package": "Пакет документов", "contents": "Состав пакета", "to": "Кому", "from": "От",
           "date": "Дата", "signature": "Подпись", "sources": "Официальные источники требований",
           "checked": "проверено", "beta": "Бета", "phone": "Тел."},
    "kk": {"package": "Құжаттар топтамасы", "contents": "Топтама құрамы", "to": "Кімге", "from": "Кімнен",
           "date": "Күні", "signature": "Қолы", "sources": "Талаптардың ресми дереккөздері",
           "checked": "тексерілді", "beta": "Бета", "phone": "Тел."},
}


class _Fmt(dict):
    def __missing__(self, key: str) -> str:
        return ""


def _answered(name: str | None, facts: dict[str, Any], skipped: list[str]) -> bool:
    return bool(name) and name in facts and name not in skipped and str(facts[name]).strip() != ""


def _applies(line: PackageLine | PackageSection, facts: dict[str, Any], skipped: list[str]) -> bool:
    if line.if_ and not _answered(line.if_, facts, skipped):
        return False
    unless = getattr(line, "unless", None)
    return not (unless and _answered(unless, facts, skipped))


def _text(line: PackageLine, lang: str, default_lang: str, fmt: dict[str, Any]) -> str:
    raw = line.t.get(lang) or line.t.get(default_lang) or next(iter(line.t.values()), "")
    return raw.format_map(_Fmt(fmt)).strip()


def sections(spec: ActionSpec, lang: str, default_lang: str, facts: dict[str, Any], skipped: list[str],
             fmt: dict[str, Any]) -> list[dict[str, Any]]:
    """The package documents that apply to this person, with their text filled in."""
    out = []
    for sec in spec.package:
        if not _applies(sec, facts, skipped):
            continue
        title = sec.title.get(lang) or sec.title.get(default_lang) or sec.id
        paragraphs = [p for p in (_text(x, lang, default_lang, fmt) for x in sec.text if _applies(x, facts, skipped)) if p]
        check = [c for c in (_text(x, lang, default_lang, fmt) for x in sec.check if _applies(x, facts, skipped)) if c]
        out.append({"id": sec.id, "title": title, "paragraphs": paragraphs, "check": check,
                    "signature": sec.signature})
    return out


def checklist(spec: ActionSpec, lang: str, default_lang: str, facts: dict[str, Any], skipped: list[str],
              fmt: dict[str, Any]) -> list[str]:
    """Personal checklist: every checklist item of the package that applies to this person."""
    return [item for s in sections(spec, lang, default_lang, facts, skipped, fmt) for item in s["check"]]


def labels(lang: str, default_lang: str) -> dict[str, str]:
    return {**LABELS.get(default_lang, LABELS["ru"]), **LABELS.get(lang, {})}


def sources(sc: Scenario, lang: str, default_lang: str) -> list[dict[str, str]]:
    return [{"title": s.title.get(lang) or s.title.get(default_lang) or s.url, "url": s.url,
             "checked_on": s.checked_on.strftime("%d.%m.%Y") if s.checked_on else ""} for s in sc.sources]
