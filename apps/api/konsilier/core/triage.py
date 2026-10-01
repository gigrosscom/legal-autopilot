"""«Юридический разбор» of the first message, before the scenario (owner 01.10): category and subcategory, the subject,
the parties, where the case is filed and whether a pre-court step is required, the scenario, the confidence and what
is missing. One model call (``ai.qualify`` with the rules) plus a check by the pack's own words, so a scenario the
lawyer ruled out for these words is never a confident document. The rules — categories, routes, the words for and
against each scenario — are the pack's (``triage.yaml``): the lawyer edits them without code; this module knows no
country."""
from __future__ import annotations

import re
from typing import Any


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower().replace("ё", "е"))


def _hits(words: list[str] | tuple[str, ...], text: str) -> list[str]:
    t = _norm(text)
    return [w for w in words or () if _norm(w) and _norm(w) in t]


def blocked_by(rules: dict[str, Any], scenario_id: str | None, text: str) -> list[str]:
    """The words that rule this scenario out for this text (the lawyer's «не выбирать»)."""
    sc = (rules.get("scenarios") or {}).get(scenario_id or "")
    return _hits(sc.get("not") or [], text) if sc else []


def guess(rules: dict[str, Any], text: str, allowed: set[str] | None = None) -> dict[str, Any]:
    """The pack's words alone: the best scenario (most «за» words, none «против»; the first listed on a tie), else
    a category with no scenario. A cross-check of the model and the answer when the model is down."""
    best: tuple[int, str] | None = None
    for sid, sc in (rules.get("scenarios") or {}).items():
        if allowed is not None and sid not in allowed:
            continue
        n = len(_hits(sc.get("choose") or [], text))
        if n and not blocked_by(rules, sid, text) and (best is None or n > best[0]):
            best = (n, sid)
    if best:
        sc = rules["scenarios"][best[1]]
        return {"scenario_id": best[1], "category": sc.get("category"), "subcategory": sc.get("subcategory"),
                "subject": (sc.get("subject") or [None])[0], "hits": _hits(sc.get("choose") or [], text)}
    for category, words in (rules.get("no_scenario") or {}).items():
        if _hits(words, text):
            return {"scenario_id": None, "category": category, "subcategory": None, "subject": None,
                    "hits": _hits(words, text)}
    return {"scenario_id": None, "category": None, "subcategory": None, "subject": None, "hits": []}


def route(rules: dict[str, Any], category: str | None) -> dict[str, Any] | None:
    """Where the case is filed and whether a pre-court step is required — the lawyer's table, never the model's."""
    cat = (rules.get("categories") or {}).get(category or "")
    return dict(cat.get("route") or {}) if cat else None


def prompt_rules(rules: dict[str, Any]) -> dict[str, Any]:
    """What the model is given to decide by: the lists to choose from and each scenario's words."""
    cats = rules.get("categories") or {}
    return {
        "categories": {k: {"title": v.get("title"), "subcategories": v.get("subcategories") or {}} for k, v in cats.items()},
        "subjects": rules.get("subjects") or {},
        "client_kinds": rules.get("client_kinds") or {},
        "respondent_kinds": rules.get("respondent_kinds") or {},
    }


def scenario_words(rules: dict[str, Any], scenario_id: str) -> dict[str, list[str]]:
    sc = (rules.get("scenarios") or {}).get(scenario_id) or {}
    return {"choose_when": list(sc.get("choose") or []), "never_when": list(sc.get("not") or [])}


def result(rules: dict[str, Any], out: dict[str, Any], text: str, scenario_id: str | None, confidence: float,
           reason: str) -> dict[str, Any]:
    """The «юридический разбор» as kept in the case and shown in /ops."""
    by_words = guess(rules, text)
    category = out.get("category") or by_words.get("category")
    sc = (rules.get("scenarios") or {}).get(scenario_id or "") or {}
    if scenario_id and sc.get("category") and not out.get("category"):
        category = sc["category"]
    return {
        "version": rules.get("version"),
        "category": category,
        "subcategory": out.get("subcategory") or (sc.get("subcategory") if scenario_id else by_words.get("subcategory")),
        "subject": out.get("subject"),
        "client_kind": out.get("client_kind"),
        "respondent_kind": out.get("respondent_kind"),
        "channel": out.get("channel"),
        "scenario_id": scenario_id,
        "confidence": round(float(confidence), 2),
        "missing": [str(m) for m in out.get("missing") or []][:5],
        "question": (out.get("question") or "").strip() or None,
        "reason": reason,
        "route": route(rules, category),
        "by_words": {"scenario_id": by_words.get("scenario_id"), "category": by_words.get("category"),
                     "hits": by_words.get("hits")},
        "agrees": by_words.get("scenario_id") in (None, scenario_id),
    }
