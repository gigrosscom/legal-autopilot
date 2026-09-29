"""Aqyl-Bench: score the running system (routing and document reading) on a fixed set of cases.

Routing items run the real intake — ``engine.start_case`` on a throw-away database, with the configured model —
and compare the dispute it lands on (the scenario's taxonomy or the universal route) with the expected one.
Extraction items read a document for a scenario and compare the facts. Scenario classification examples are
added as a second, easier set ("scenario_example"): they are also shown to the classifier, so the lawyer's set
("team"/"lawyer") is the real score.
"""
from __future__ import annotations

import json
import tempfile
import time
from collections import Counter
from pathlib import Path
from typing import Any

from ..config import Settings
from ..core import ai
from ..core.fields import FieldError, normalize
from ..core.llm import RedactingLLM
from ..core.models import Base, User
from ..core.pii import PiiVault


def load(path: Path) -> list[dict[str, Any]]:
    files = sorted(path.rglob("*.jsonl")) if path.is_dir() else [path]
    return [json.loads(line) for f in files for line in f.read_text("utf-8").splitlines() if line.strip()]


def scenario_items(packs: Any, country: str) -> list[dict[str, Any]]:
    out = []
    for sc in packs.published(country):
        for lang, examples in sc.classification.examples.items():
            for i, text in enumerate(examples, 1):
                out.append({"id": f"{sc.id}-{lang}-{i}", "task": "routing", "country": country, "language": lang,
                            "text": text, "expect": sc.taxonomy, "accept": [], "source": "scenario_example"})
    return [i for i in out if i["expect"]]


def run(settings: Settings, items: list[dict[str, Any]], *, with_examples: bool = True,
        limit: int | None = None) -> dict[str, Any]:
    from ..container import build_container

    with tempfile.TemporaryDirectory() as tmp:
        s = settings.model_copy(update={"database_url": f"sqlite:///{tmp}/bench.db", "background_jobs": "off",
                                        "scheduler_interval_seconds": 0, "storage_backend": "local",
                                        "storage_local_dir": Path(tmp) / "files"})
        container = build_container(s)
        Base.metadata.create_all(container.engine_db)
        engine = container.engine
        if with_examples:
            items = items + [i for c in sorted({i["country"] for i in items if i.get("country")})
                             for i in scenario_items(container.packs, c)]
        if limit:
            items = items[:limit]
        results = []
        for item in items:
            t0 = time.monotonic()
            try:
                got = _routing(container, item) if item["task"] == "routing" else _extraction(container, item)
                ok = _ok(item, got)
            except Exception as e:  # noqa: BLE001 — a failing item is a result, not a crash
                got, ok = {"error": f"{type(e).__name__}: {e}"}, False
            results.append({"id": item["id"], "task": item["task"], "source": item.get("source"), "ok": ok,
                            "expect": item["expect"], "got": got, "seconds": round(time.monotonic() - t0, 2)})
        container.engine_db.dispose()
    by: dict[str, Counter] = {}
    for r in results:
        key = f"{r['task']}/{'examples' if r['source'] == 'scenario_example' else 'cases'}"
        by.setdefault(key, Counter())["ok" if r["ok"] else "fail"] += 1
    score = {k: {"ok": v["ok"], "total": v["ok"] + v["fail"], "accuracy": round(v["ok"] / (v["ok"] + v["fail"]), 3)}
             for k, v in sorted(by.items())}
    return {"model": getattr(engine.llm_provider, "model", type(engine.llm_provider).__name__),
            "score": score, "results": results}


def _routing(container: Any, item: dict[str, Any]) -> dict[str, Any]:
    engine = container.engine
    with container.session_factory() as session:
        user = User(language=item.get("language", "ru"), country=item.get("country"), is_test=True, source="bench")
        session.add(user)
        session.flush()
        case, _ = engine.start_case(session, user, item["text"], language=item.get("language"),
                                    country=item.get("country"))
        dispute = None
        if case.scenario_id and not case.scenario_id.startswith(f"{(case.jurisdiction or '').lower()}.generic."):
            dispute = engine.scenario_of(case).taxonomy
        dispute = dispute or (case.taxonomy or {}).get("dispute_id")
        out = {"dispute": dispute, "scenario": case.scenario_id, "level": case.coverage_level}
        session.rollback()
        return out


def _extraction(container: Any, item: dict[str, Any]) -> dict[str, Any]:
    packs = container.packs
    sc = packs.scenario(item["scenario"])
    pack = packs.pack(sc.jurisdiction)
    llm = RedactingLLM(container.engine.llm_provider, PiiVault())
    facts, _, _ = ai.extract_evidence(llm, sc, pack, item.get("language", "ru"), item["text"])
    today = pack.local_now().date()
    out = {}
    for name, raw in facts.items():
        try:
            out[name] = str(normalize(sc.field(name), raw, today=today))
        except (FieldError, KeyError):
            continue
    return {"facts": out}


def _ok(item: dict[str, Any], got: dict[str, Any]) -> bool:
    if item["task"] == "routing":
        return got.get("dispute") in [item["expect"], *item.get("accept", [])]
    facts = got.get("facts", {})

    def same(a: str, b: str) -> bool:
        try:
            return float(a) == float(b)
        except ValueError:
            return a.strip().lower() == b.strip().lower()
    return all(k in facts and same(str(facts[k]), str(v)) for k, v in item["expect"].items())
