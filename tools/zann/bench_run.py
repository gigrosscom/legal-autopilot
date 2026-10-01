#!/usr/bin/env python3
"""Zann-Bench runner: open models from the NVIDIA API Catalog answer the bench's legal questions, with our retrieval
(RAG over the Zann article index) and without it, and are scored on citations.

    python tools/zann/bench_run.py --bench team/zann/bench/kz-v1.jsonl                 # every model, rag + norag
    python tools/zann/bench_run.py --bench … --models meta/llama-3.3-70b-instruct --mode rag --limit 20
    python tools/zann/bench_run.py --bench … --index-db postgresql+psycopg://…        # RAG + «is it in the corpus»
    python tools/zann/bench_run.py --list-models                                      # what the catalog serves
    python tools/zann/bench_run.py --bench … --dry-run                                # fake model, no network

Endpoint: https://integrate.api.nvidia.com/v1 (OpenAI-compatible), key from the environment NVIDIA_API_KEY (never
from a file or the command line). The free tier allows up to 40 requests a minute: a sliding-window limiter keeps
every run at or under --rpm (at most 40). No paid API is called.

Bench line (JSONL, one question per line):
    {"id": "kz-qa-ru-001", "lang": "ru", "question": "…", "reference_answer": "…",
     "act": "K1500000414", "article": "113", "act_title": "Трудовой кодекс Республики Казахстан",   # act_title optional
     "accept": [["K1500000414", "113-1"]], "verified_by": "Фамилия И.О." | null, "source": "team", "note": ""}

Scores per answer:
- citation: the answer cites the expected article of the expected act (or an accepted pair);
- invented: cited norms that are not real — an article not in our corpus (with --index-db), or the expected article
  number given with another act (wrong act);
- overlap: word F1 between the answer and the reference answer (crude stems);
- latency: seconds of the model call.
Output: a markdown report docs/zann-bench-<date>.md (table per model × mode, then per language) and the raw answers
as JSONL (--raw, default data/zann/bench-<date>.jsonl, not in git).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import sys
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Callable, Protocol

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "apps" / "api"))

from konsilier.zann.search import ACT_ALIASES, references  # noqa: E402

BASE_URL = "https://integrate.api.nvidia.com/v1"
MAX_RPM = 40  # the free tier of the NVIDIA API Catalog
# Candidates on the catalog (check with --list-models; a model the catalog does not serve is skipped after its first
# 404). KazLLM (ISSAI) is not on the catalog as far as we know; add it here if it appears.
DEFAULT_MODELS = (
    "qwen/qwen3-235b-a22b",
    "meta/llama-3.3-70b-instruct",
    "meta/llama-4-maverick-17b-128e-instruct",
    "google/gemma-3-27b-it",
    "nvidia/llama-3.3-nemotron-super-49b-v1.5",
    "nvidia/nvidia-nemotron-nano-9b-v2",
)
RAG_ARTICLES = 5
RAG_CHARS = 1500  # of each article in the prompt

SYSTEM = {
    "ru": ("Вы — юридический помощник по праву Республики Казахстан. Ответьте на вопрос по-русски, 3–6 предложений, "
           "простыми словами. Укажите норму в виде «ст. N <название акта>». Называйте только те статьи, в которых "
           "уверены; если не уверены — назовите закон без номера статьи."),
    "kk": ("Сіз Қазақстан Республикасының құқығы бойынша заң көмекшісісіз. Сұраққа қазақ тілінде 3–6 сөйлеммен, "
           "қарапайым тілмен жауап беріңіз. Норманы «<акт атауы> N-бабы» түрінде көрсетіңіз. Тек сенімді баптарды "
           "атаңыз; сенімді болмасаңыз — заңды бап нөмірінсіз атаңыз."),
}
RAG_NOTE = {
    "ru": "Статьи из официальных текстов (adilet) — опирайтесь только на них и цитируйте их:\n",
    "kk": "Ресми мәтіндердегі баптар (adilet) — тек соларға сүйеніп, соларды келтіріңіз:\n",
}


# ---------------------------------------------------------------------------------------------------- bench
@dataclass
class Item:
    id: str
    lang: str
    question: str
    reference_answer: str
    act: str
    article: str
    act_title: str = ""
    accept: list[list[str]] = field(default_factory=list)
    verified_by: str | None = None
    source: str = ""
    note: str = ""


def load_bench(path: Path) -> list[Item]:
    items = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        d = json.loads(line)
        missing = [k for k in ("id", "lang", "question", "reference_answer", "act", "article") if not d.get(k)]
        if missing:
            raise ValueError(f"{path}:{n}: missing {', '.join(missing)}")
        items.append(Item(**{k: d[k] for k in Item.__dataclass_fields__ if k in d}))
    return items


# ---------------------------------------------------------------------------------------------------- limiter
class RateLimiter:
    """At most ``rpm`` calls in any 60 seconds (sliding window), shared by every thread of the run."""

    def __init__(self, rpm: int, clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep):
        self.rpm, self.clock, self.sleep = max(1, min(rpm, MAX_RPM)), clock, sleep
        self.calls: deque[float] = deque()
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            while True:
                now = self.clock()
                while self.calls and now - self.calls[0] >= 60:
                    self.calls.popleft()
                if len(self.calls) < self.rpm:
                    self.calls.append(now)
                    return
                self.sleep(60 - (now - self.calls[0]) + 0.01)


# ---------------------------------------------------------------------------------------------------- models
class Model(Protocol):
    def __call__(self, model: str, messages: list[dict[str, str]]) -> str: ...


class ModelUnavailable(Exception):
    pass


class NvidiaCatalog:
    """OpenAI-compatible chat completions on the NVIDIA API Catalog, through the limiter, retrying 429 / 5xx."""

    def __init__(self, api_key: str, limiter: RateLimiter, base_url: str = BASE_URL, timeout: float = 120,
                 max_tokens: int = 700, retries: int = 3, client: Any = None,
                 sleep: Callable[[float], None] = time.sleep):
        import httpx

        self.limiter, self.base, self.max_tokens, self.retries = limiter, base_url.rstrip("/"), max_tokens, retries
        self.sleep = sleep
        self.client = client or httpx.Client(timeout=timeout)
        self.client.headers.update({"Authorization": f"Bearer {api_key}", "Accept": "application/json"})

    def models(self) -> list[str]:
        self.limiter.wait()
        r = self.client.get(f"{self.base}/models")
        r.raise_for_status()
        return sorted(m["id"] for m in r.json().get("data", []))

    def __call__(self, model: str, messages: list[dict[str, str]]) -> str:
        body = {"model": model, "messages": messages, "temperature": 0.2, "top_p": 0.9, "max_tokens": self.max_tokens,
                "stream": False}
        for attempt in range(self.retries + 1):
            self.limiter.wait()
            r = self.client.post(f"{self.base}/chat/completions", json=body)
            if r.status_code in (404, 400) and "model" in r.text.lower() and attempt == 0:
                raise ModelUnavailable(f"{model}: {r.status_code} {r.text[:200]}")
            if r.status_code == 429 or r.status_code >= 500:
                if attempt == self.retries:
                    r.raise_for_status()
                ra = r.headers.get("Retry-After", "")
                self.sleep(float(ra) if ra.replace(".", "", 1).isdigit() else 5 * 2 ** attempt)
                continue
            r.raise_for_status()
            msg = r.json()["choices"][0]["message"]
            text = msg.get("content") or ""
            return re.sub(r"(?s)<think>.*?</think>", "", text).strip()  # reasoning models: the answer only
        raise RuntimeError("unreachable")


class FakeModel:
    """--dry-run and tests: no network. With articles in the prompt it cites the first one; without, it cites the
    expected article of a wrong act — so both «correct citation» and «invented norm» paths are exercised."""

    def __call__(self, model: str, messages: list[dict[str, str]]) -> str:
        user = messages[-1]["content"]
        m = re.search(r"\[(ст\. [^,\]]+|\d+[^\]]*?-бап)[^\]]*\]\s*\(([A-Z]\d{9,10}_?)\)", user)
        if m:
            return f"Да. Это прямо указано: {m.group(1).split(',')[0]} ({m.group(2)})."
        return "Скорее всего, применяется ст. 999 Трудового кодекса."


# ---------------------------------------------------------------------------------------------------- retrieval
class Corpus:
    """The Zann index (zann_articles) for RAG and for checking that a cited article exists."""

    def __init__(self, url: str):
        from konsilier.core.db import make_engine, make_session_factory
        from konsilier.zann.search import LawIndex

        self.sf = make_session_factory(make_engine(url))
        self.index = LawIndex(self.sf, min_score=0)
        self._titles: list[tuple[str, str]] | None = None

    def retrieve(self, question: str, lang: str, k: int = RAG_ARTICLES) -> list[Any]:
        return self.index.search(question, prefer_lang=lang, limit=k)

    def titles(self) -> list[tuple[str, str]]:
        if self._titles is None:
            from sqlalchemy import select

            from konsilier.core.models import ZannFile

            with self.sf() as s:
                self._titles = [(c, (t or "").lower()) for c, t in s.execute(select(ZannFile.code, ZannFile.title))]
        return self._titles

    def exists(self, code: str, number: str) -> bool:
        from sqlalchemy import select

        from konsilier.core.models import ZannArticle

        with self.sf() as s:
            return s.scalar(select(ZannArticle.id).where(ZannArticle.code == code, ZannArticle.number == number)
                            .limit(1)) is not None


def rag_block(hits: list[Any], lang: str) -> str:
    parts = [f"[{h.citation}] ({h.code}) {h.url}\n{h.text[:RAG_CHARS]}" for h in hits]
    return RAG_NOTE.get(lang, RAG_NOTE["ru"]) + "\n\n".join(parts)


# ---------------------------------------------------------------------------------------------------- scoring
KK_REF_RE = re.compile(r"(?i)([\w\s«»\"()-]{0,80}?)(\d+(?:-\d+)?)\s*-?\s*(?:бап|баб)\w*")


@dataclass
class Cited:
    article: str
    code: str | None   # resolved act, None when the act could not be told
    act: str           # how the answer named it


def _codes_for(frags: tuple[str, ...], item: Item, corpus: Corpus | None) -> str | None:
    for f in frags:
        if re.fullmatch(r"[A-Z]\d{9,10}_?", f):
            return f
    expected = (item.act_title or "").lower()
    for f in frags:
        if expected and f in expected:
            return item.act
    if corpus is not None:
        for f in frags:
            hits = [c for c, t in corpus.titles() if f in t]
            if hits:
                return item.act if item.act in hits else hits[0]
    if expected:  # a named act that is not the expected one (and not in the corpus): another act
        return "name:" + frags[0]
    return None


def citations(answer: str, item: Item, corpus: Corpus | None = None) -> list[Cited]:
    """The (article, act) pairs an answer cites. Russian order «ст. 113 ТК»; Kazakh order «Еңбек кодексінің
    113-бабы» (the act comes first) is read too."""
    out: list[Cited] = []
    for num, frags in references(answer):
        out.append(Cited(num, _codes_for(frags, item, corpus), "/".join(frags)))
    for m in KK_REF_RE.finditer(answer):
        before, num = m.group(1).lower(), m.group(2)
        frags = tuple(v for k, vs in ACT_ALIASES.items() for v in vs if k.split()[0] in before and len(k) > 3)
        code = _codes_for(frags, item, corpus) if frags else None
        if code and not any(c.article == num and c.code == code for c in out):
            out.append(Cited(num, code, "/".join(frags)))
    for code in re.findall(r"\b([A-Z]\d{9,10}_?)\b", answer):  # «(K1500000414)» after a citation
        for c in out:
            if c.code is None:
                c.code = code
    seen, uniq = set(), []
    for c in out:
        if (c.article, c.code) not in seen:
            seen.add((c.article, c.code))
            uniq.append(c)
    return uniq


def _stems(text: str) -> list[str]:
    return [w[:6] for w in re.findall(r"[^\W\d_]{3,}", text.lower().replace("ё", "е"))]


def overlap(answer: str, reference: str) -> float:
    a, r = _stems(answer), _stems(reference)
    if not a or not r:
        return 0.0
    common = sum(min(a.count(w), r.count(w)) for w in set(a))
    if not common:
        return 0.0
    p, rc = common / len(a), common / len(r)
    return round(2 * p * rc / (p + rc), 3)


def score(answer: str, item: Item, corpus: Corpus | None = None) -> dict[str, Any]:
    cited = citations(answer, item, corpus)
    good = {(item.act, item.article)} | {(a, n) for a, n in item.accept}
    correct = any((c.code, c.article) in good for c in cited)
    invented = []
    for c in cited:
        if (c.code, c.article) in good:
            continue
        if c.article == item.article and c.code is not None and c.code != item.act:
            invented.append({**asdict(c), "why": "wrong_act"})
        elif (corpus is not None and c.code is not None and not c.code.startswith("name:")
              and not corpus.exists(c.code, c.article)):
            invented.append({**asdict(c), "why": "not_in_corpus"})
    return {"cited": [asdict(c) for c in cited], "correct_citation": correct, "invented": invented,
            "overlap": overlap(answer, item.reference_answer)}


# ---------------------------------------------------------------------------------------------------- run
def messages_for(item: Item, hits: list[Any] | None) -> list[dict[str, str]]:
    user = item.question if not hits else f"{rag_block(hits, item.lang)}\n\nВопрос: {item.question}"
    return [{"role": "system", "content": SYSTEM.get(item.lang, SYSTEM["ru"])}, {"role": "user", "content": user}]


def run(items: list[Item], models: list[str], modes: list[str], model: Model, corpus: Corpus | None,
        log: Callable[[str], None] = print) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    retrieved: dict[str, list[Any]] = {}
    if "rag" in modes and corpus is not None:
        for it in items:
            t0 = time.perf_counter()
            retrieved[it.id] = corpus.retrieve(it.question, it.lang)
            retrieved[it.id + ":ms"] = round((time.perf_counter() - t0) * 1000, 1)  # type: ignore[assignment]
    for name in models:
        skip = False
        for mode in modes:
            if mode == "rag" and corpus is None:
                continue
            for it in items:
                row: dict[str, Any] = {"id": it.id, "lang": it.lang, "model": name, "mode": mode,
                                       "verified": bool(it.verified_by)}
                if skip:
                    row.update(error="model unavailable", answer="", latency=None)
                    rows.append(row)
                    continue
                hits = retrieved.get(it.id) if mode == "rag" else None
                if hits is not None:
                    row["retrieved"] = [{"code": h.code, "article": h.number} for h in hits]
                    row["retrieval_hit"] = any(h.code == it.act and h.number == it.article for h in hits)
                    row["retrieval_ms"] = retrieved.get(it.id + ":ms")
                t0 = time.perf_counter()
                try:
                    answer = model(name, messages_for(it, hits))
                    row.update(answer=answer, latency=round(time.perf_counter() - t0, 2), error=None)
                    row.update(score(answer, it, corpus))
                except ModelUnavailable as e:
                    skip = True
                    row.update(error=str(e)[:300], answer="", latency=None)
                    log(f"  {name}: not served by the catalog, skipped")
                except Exception as e:  # noqa: BLE001 — one failed call must not stop the run
                    row.update(error=f"{type(e).__name__}: {e}"[:300], answer="", latency=round(time.perf_counter() - t0, 2))
                rows.append(row)
            done = [r for r in rows if r["model"] == name and r["mode"] == mode]
            log(f"  {name} [{mode}]: {sum(1 for r in done if r.get('correct_citation'))}/{len(done)} correct citations")
    return rows


def _pct(n: int, d: int) -> str:
    return f"{100 * n / d:.0f} %" if d else "—"


def _p(values: list[float], q: float) -> str:
    if not values:
        return "—"
    v = sorted(values)
    return f"{v[min(len(v) - 1, int(q * len(v)))]:.1f}"


def summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for r in rows:
        groups.setdefault((r["model"], r["mode"], ""), []).append(r)
        groups.setdefault((r["model"], r["mode"], r["lang"]), []).append(r)
    out = []
    for (model, mode, lang), rs in groups.items():
        ok = [r for r in rs if not r.get("error")]
        lat = [r["latency"] for r in ok if r.get("latency") is not None]
        out.append({"model": model, "mode": mode, "lang": lang, "n": len(rs), "answered": len(ok),
                    "correct": sum(1 for r in ok if r.get("correct_citation")),
                    "with_invented": sum(1 for r in ok if r.get("invented")),
                    "invented": sum(len(r.get("invented") or []) for r in ok),
                    "overlap": round(statistics.mean([r["overlap"] for r in ok]), 3) if ok else None,
                    "p50": _p(lat, 0.5), "p95": _p(lat, 0.95),
                    "retrieval_hit": sum(1 for r in rs if r.get("retrieval_hit")) if mode == "rag" else None})
    return out


def report(rows: list[dict[str, Any]], bench: Path, items: list[Item], day: str, dry: bool, corpus: bool) -> str:
    summary = summarize(rows)
    verified = sum(1 for it in items if it.verified_by)
    langs = sorted({it.lang for it in items})
    lines = [f"# Zann-Bench — {day}", "",
             f"Набор: `{bench.as_posix()}` — {len(items)} вопросов ({', '.join(langs)}), проверено юристом: {verified}.",
             "Модели: NVIDIA API Catalog (бесплатный уровень, ≤ 40 запросов/мин)" + (" — **пробный прогон с "
             "фальшивой моделью, цифры не о моделях**" if dry else "") + ".",
             "RAG: статьи из индекса Zann (поиск по корпусу adilet), до 5 статей в запросе." if corpus else
             "RAG не запускался: нет базы индекса (--index-db); «выдуманные» — только «не тот акт».", "",
             "Метрики: **цитата** — названа ожидаемая статья ожидаемого акта; **выдуманные** — ответы, где есть статья, "
             "которой нет в корпусе, или ожидаемый номер статьи с другим актом; **пересечение** — F1 слов с эталоном; "
             "**время** — секунды на ответ (p50 / p95).", "",
             "| Модель | Режим | Ответов | Цитата верна | С выдуманными нормами | Пересечение | Время p50 / p95, с |"
             + (" Поиск нашёл статью |" if corpus else ""),
             "|---|---|---:|---:|---:|---:|---:|" + ("---:|" if corpus else "")]
    for s in sorted((s for s in summary if not s["lang"]), key=lambda s: (s["model"], s["mode"])):
        lines.append(f"| {s['model']} | {s['mode']} | {s['answered']}/{s['n']} | {_pct(s['correct'], s['answered'])} "
                     f"| {_pct(s['with_invented'], s['answered'])} | {s['overlap'] if s['overlap'] is not None else '—'} "
                     f"| {s['p50']} / {s['p95']} |"
                     + ((f" {_pct(s['retrieval_hit'], s['n'])} |" if s["retrieval_hit"] is not None else " — |")
                        if corpus else ""))
    if len(langs) > 1:
        lines += ["", "## По языкам", "", "| Модель | Режим | Язык | Ответов | Цитата верна | С выдуманными нормами |",
                  "|---|---|---|---:|---:|---:|"]
        for s in sorted((s for s in summary if s["lang"]), key=lambda s: (s["model"], s["mode"], s["lang"])):
            lines.append(f"| {s['model']} | {s['mode']} | {s['lang']} | {s['answered']}/{s['n']} "
                         f"| {_pct(s['correct'], s['answered'])} | {_pct(s['with_invented'], s['answered'])} |")
    errors = [r for r in rows if r.get("error")]
    if errors:
        lines += ["", f"Ошибок вызова: {len(errors)} (подробно — в сыром JSONL)."]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--bench", type=Path, help="JSONL with the questions (format in the module docstring)")
    ap.add_argument("--models", default=",".join(DEFAULT_MODELS), help="comma-separated catalog model ids")
    ap.add_argument("--mode", choices=("both", "rag", "norag"), default="both")
    ap.add_argument("--index-db", default=os.environ.get("ZANN_INDEX_DB", ""),
                    help="database URL with zann_articles (RAG and the corpus check)")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--rpm", type=int, default=MAX_RPM, help=f"requests per minute, at most {MAX_RPM}")
    ap.add_argument("--max-tokens", type=int, default=700)
    ap.add_argument("--date", default=date.today().isoformat())
    ap.add_argument("--report", type=Path, help="markdown report (default docs/zann-bench-<date>.md)")
    ap.add_argument("--raw", type=Path, help="raw answers JSONL (default data/zann/bench-<date>.jsonl)")
    ap.add_argument("--dry-run", action="store_true", help="fake model, no network, no key")
    ap.add_argument("--list-models", action="store_true", help="print the catalog's model ids and exit")
    a = ap.parse_args(argv)

    key = os.environ.get("NVIDIA_API_KEY", "")
    limiter = RateLimiter(a.rpm)
    if a.list_models:
        if not key:
            print("NVIDIA_API_KEY is not set", file=sys.stderr)
            return 2
        print("\n".join(NvidiaCatalog(key, limiter).models()))
        return 0
    if not a.bench:
        ap.error("--bench is required")
    items = load_bench(a.bench)[: a.limit] if a.limit else load_bench(a.bench)
    if a.dry_run:
        model: Model = FakeModel()
    elif not key:
        print("NVIDIA_API_KEY is not set (or use --dry-run)", file=sys.stderr)
        return 2
    else:
        model = NvidiaCatalog(key, limiter, max_tokens=a.max_tokens)
    corpus = Corpus(a.index_db) if a.index_db else None
    modes = ["rag", "norag"] if a.mode == "both" else [a.mode]
    models = [m.strip() for m in a.models.split(",") if m.strip()]
    if a.dry_run:
        models = ["fake/dry-run"]
    print(f"{len(items)} questions × {len(models)} models × {modes}; ≤ {limiter.rpm} requests/min")
    rows = run(items, models, modes, model, corpus)
    raw = a.raw or REPO / "data" / "zann" / f"bench-{a.date}.jsonl"
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    out = a.report or REPO / "docs" / f"zann-bench-{a.date}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        bench_name = a.bench.resolve().relative_to(REPO)
    except ValueError:
        bench_name = a.bench
    out.write_text(report(rows, bench_name, items, a.date, a.dry_run, corpus is not None), encoding="utf-8")
    print(f"report: {out}\nraw:    {raw}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
