#!/usr/bin/env python3
"""Zann-Bench runner: open models from the NVIDIA API Catalog answer the open part of Zann-Bench KZ v1, with our
retrieval (RAG over the Zann article index) and without it; answers are scored by simple, explainable rules and,
optionally, by a free LLM judge (marked separately).

    python tools/zann/bench_run.py --list-models                                       # what the catalog lists
    python tools/zann/bench_run.py --bench kz-v1.jsonl --index-db sqlite:///data/zann/index.sqlite \\
        --models google/gemma-4-31b-it,nvidia/nemotron-3-super-120b-a12b --mode norag     # answers → raw JSONL
    python tools/zann/bench_run.py --bench … --judge nvidia/nemotron-3-ultra-550b-a55b --raw data/zann/….jsonl
    python tools/zann/bench_run.py --bench … --report-only --raw data/zann/….jsonl      # tables from raw answers
    python tools/zann/bench_run.py --bench … --dry-run                                   # fake model, no network

Bench: team/zann/bench/kz-v1.jsonl (branch claude/ai-team; format in team/zann/bench/README.md). **Only items with
split == "open" are ever loaded**: hidden items (the exam) are dropped line by line in ``open_items`` before
anything else sees them — they never reach a prompt, a judge, the raw file or the report.

Endpoint: https://integrate.api.nvidia.com/v1 (OpenAI-compatible), key from the environment NVIDIA_API_KEY (never
from a file or the command line, never printed). The free tier allows up to 40 requests a minute: one sliding-window
limiter is shared by every thread and counts retries too, so a run stays at or under --rpm (at most 40). No paid API.

Prompt: the chat's own system prompt (konsilier/chat.py SYSTEM, answer in the question's language). The bench has
no tools, so the tool rules are replaced: without retrieval the model may state an article only when sure; with
retrieval it gets the chat's LAW_RULE wording and the top articles of the local index (konsilier/zann/search.py).

Scores per answer (deterministic — string/keyword matching and citation parsing, see ``score``):
- norm: each ``must_cite`` (act + article) cited → 1; the act named without the article → 1/3;
- addressee / document (routing, drafting_check, refusal): the bodies and document kinds of ``expected`` found in
  the answer (keyword classes);
- deadline (deadline, routing): each «number + unit» of ``expected.deadline`` found in the answer;
- must_include (drafting_check), facts (extraction), escalation (``escalate_to_lawyer``), language (the question's);
- invented norm: an article cited for an act of our corpus that does not exist in it, or a foreign (RF) law. An
  answer with an invented norm scores 0 (README: «красный флаг»).
- judge (optional, --judge): a free catalog model reads the question, the reference answer, the red flags and the
  answer, and says which red flags the answer commits and whether it invents a norm/deadline/amount/body. The
  «with judge» total also zeroes those answers. Judge-based numbers are always labelled as such.
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
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Callable, Iterator, Protocol

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "apps" / "api"))

BASE_URL = "https://integrate.api.nvidia.com/v1"
MAX_RPM = 40  # the free tier of the NVIDIA API Catalog
# Served by the catalog on 01.10.2026 (checked one request each; Qwen, Llama 3.3/4, Mistral Large answer 404/410).
DEFAULT_MODELS = (
    "nvidia/nemotron-3-ultra-550b-a55b",
    "nvidia/nemotron-3-super-120b-a12b",
    "google/gemma-4-31b-it",
    "meta/llama-3.2-90b-vision-instruct",
    "openai/gpt-oss-20b",
)
RAG_ARTICLES = 5
RAG_CHARS = 1500  # of each article in the prompt
LANG_NAME = {"ru": "Russian", "kk": "Kazakh"}

BENCH_NO_TOOLS = ("This is a test without tools: you cannot open the official texts. State an article number only "
                  "if you are sure of it; otherwise name the law or code by its title without an article number.")
BENCH_RAG = ("Articles of the law found in our copy of the official texts (adilet) for the last message are given "
             "below (may be off-topic). Cite an article you rely on as «ст. N <act>» (kk: «<act> N-бабы»), and only "
             "for what its text says. There are no tools in this test.")


# ---------------------------------------------------------------------------------------------------- bench
@dataclass
class Norm:
    code: str      # adilet code from the must_cite URL
    article: str   # the article number («30», «42-4»)
    act: str       # as the bench names it
    raw: str       # «ст. 30 п. 1»


@dataclass
class Item:
    id: str
    lang: str
    question: str
    type: str
    category: str
    difficulty: int
    expected: dict[str, Any]
    must_cite: list[Norm]
    red_flags: list[str]
    verified: bool
    verified_by: str | None = None
    unverified: list[str] = field(default_factory=list)
    route: str | None = None
    facts: dict[str, Any] = field(default_factory=dict)
    topic: str = ""


def open_items(path: Path) -> Iterator[dict[str, Any]]:
    """The bench's lines with split == "open", one by one. A hidden (or unmarked) line is dropped right after it is
    parsed: it is never returned, kept, logged or counted."""
    with path.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            d = json.loads(line)
            if d.get("split") != "open":
                continue
            yield d


CODE_IN_URL = re.compile(r"/docs/([A-Z]\d{9,10}_?)")
NUM = r"\d+(?:-\d+)?"


def _norm(m: dict[str, Any]) -> Norm | None:
    code = CODE_IN_URL.search(m.get("url") or "")
    num = re.search(NUM, m.get("article") or "")
    if not code or not num:
        return None
    return Norm(code.group(1), num.group(0), m.get("act") or "", m.get("article") or "")


def load_bench(path: Path) -> list[Item]:
    items = []
    for n, d in enumerate(open_items(path), 1):
        missing = [k for k in ("id", "language", "question", "type", "expected") if not d.get(k)]
        if missing:
            raise ValueError(f"{path}: open item {n}: missing {', '.join(missing)}")
        items.append(Item(
            id=d["id"], lang=d["language"], question=d["question"], type=d["type"], category=d.get("category", ""),
            difficulty=int(d.get("difficulty") or 0), expected=d["expected"],
            must_cite=[x for x in (_norm(m) for m in d.get("must_cite") or []) if x],
            red_flags=list(d.get("red_flags") or []), verified=bool(d.get("verified")),
            verified_by=d.get("verified_by"), unverified=list(d.get("unverified") or []), route=d.get("route"),
            facts=dict(d.get("facts") or {}), topic=d.get("topic") or ""))
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


# Per-model request quirks of the catalog (a model rejects other values with 400).
MODEL_PARAMS: dict[str, dict[str, Any]] = {"moonshotai/kimi-k3": {"top_p": 0.95}}


class NvidiaCatalog:
    """OpenAI-compatible chat completions on the NVIDIA API Catalog, through the limiter, retrying 429 / 5xx /
    timeouts. A model the catalog does not serve (404, 410) raises ModelUnavailable on the first call."""

    def __init__(self, api_key: str, limiter: RateLimiter, base_url: str = BASE_URL, timeout: float = 180,
                 max_tokens: int = 700, retries: int = 5, client: Any = None,
                 sleep: Callable[[float], None] = time.sleep, temperature: float = 0.2):
        import httpx

        self.limiter, self.base, self.max_tokens, self.retries = limiter, base_url.rstrip("/"), max_tokens, retries
        self.sleep, self.temperature = sleep, temperature
        self._local = threading.local()  # the duration of this thread's last successful HTTP call
        self.client = client or httpx.Client(timeout=timeout)
        self.client.headers.update({"Authorization": f"Bearer {api_key}", "Accept": "application/json"})

    def models(self) -> list[str]:
        self.limiter.wait()
        r = self.client.get(f"{self.base}/models")
        r.raise_for_status()
        return sorted(m["id"] for m in r.json().get("data", []))

    def __call__(self, model: str, messages: list[dict[str, str]]) -> str:
        import httpx

        body = {"model": model, "messages": messages, "temperature": self.temperature, "max_tokens": self.max_tokens,
                "stream": False, **MODEL_PARAMS.get(model, {})}
        for attempt in range(self.retries + 1):
            self.limiter.wait()
            try:
                t0 = time.perf_counter()
                r = self.client.post(f"{self.base}/chat/completions", json=body)
                self._local.last = time.perf_counter() - t0
            except httpx.TransportError:
                if attempt == self.retries:
                    raise
                self.sleep(5 * 2 ** attempt)
                continue
            if (r.status_code in (404, 410) or (r.status_code == 400 and "model" in r.text.lower())) and attempt == 0:
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

    def last_latency(self) -> float | None:
        """Seconds of the last HTTP call in this thread: the model's own time, without the limiter's queue."""
        return getattr(self._local, "last", None)


class FakeModel:
    """--dry-run and tests: no network. With articles in the prompt it cites the first one; without, it cites a
    Labour Code article that does not exist — so both «correct citation» and «invented norm» paths are exercised.
    ``seen`` keeps every prompt (the tests check that hidden items never reach one)."""

    def __init__(self) -> None:
        self.seen: list[list[dict[str, str]]] = []

    def __call__(self, model: str, messages: list[dict[str, str]]) -> str:
        self.seen.append(messages)
        if model.startswith("judge"):
            return '{"red_flags": [], "invented": false}'
        system = messages[0]["content"]
        m = re.search(r'"citation": "ст\. (\d+(?:-\d+)?), ([^"]+)"', system)
        if m:
            return f"Да. Это прямо указано: ст. {m.group(1)} {m.group(2)}. Обратитесь к продавцу с претензией."
        return "Скорее всего, применяется ст. 9999 Трудового кодекса. Обратитесь в суд."


# ---------------------------------------------------------------------------------------------------- retrieval
class Corpus:
    """The Zann index (zann_articles) for RAG and for checking that a cited article exists."""

    def __init__(self, url: str):
        from sqlalchemy import select

        from konsilier.core.db import make_engine, make_session_factory
        from konsilier.core.models import ZannArticle, ZannFile
        from konsilier.zann.search import LawIndex

        self.sf = make_session_factory(make_engine(url))
        self.index = LawIndex(self.sf, min_score=0)
        self._lock = threading.Lock()
        with self.sf() as s:
            self.articles = {(c, n) for c, n in s.execute(select(ZannArticle.code, ZannArticle.number)).all() if n}
            self.acts = {c: t or "" for c, lang, t in s.execute(select(ZannFile.code, ZannFile.lang, ZannFile.title))
                         if lang == "ru"}

    def retrieve(self, question: str, lang: str, k: int = RAG_ARTICLES) -> list[Any]:
        with self._lock:  # SQLite ranking is CPU-bound anyway
            return self.index.search(question, prefer_lang=lang, limit=k, semantic=False)

    def exists(self, code: str, number: str) -> bool:
        return any((c, number) in self.articles for c in GROUPS.get(code, (code,)))


def rag_payload(hits: list[Any]) -> str:
    return json.dumps([{"citation": h.citation, "act_code": h.code, "article": h.number, "title": h.heading,
                        "url": h.url, "text": h.text[:RAG_CHARS]} for h in hits], ensure_ascii=False)


def system_prompt(lang: str, hits: list[Any] | None) -> str:
    """The chat's system prompt (konsilier/chat.py), with the bench's rules instead of tools."""
    from konsilier.chat import MORE_MARKER, NO_OFFICIAL_RULE, OFFER_MARKER, SYSTEM

    system = SYSTEM.format(country="Kazakhstan", language=LANG_NAME.get(lang, "Russian"), offer_marker=OFFER_MARKER,
                           more_marker=MORE_MARKER, portal_rule=BENCH_NO_TOOLS if hits is None else BENCH_RAG,
                           official_rule=NO_OFFICIAL_RULE)
    if hits is not None:
        system += "\n\n" + BENCH_RAG + "\nArticles for the last message:\n" + rag_payload(hits)
    return system


def messages_for(item: Item, hits: list[Any] | None) -> list[dict[str, str]]:
    return [{"role": "system", "content": system_prompt(item.lang, hits)}, {"role": "user", "content": item.question}]


def clean_answer(text: str) -> str:
    """The chat's markers out ([[MORE]], [[DOCUMENT]]): the app does not show them either."""
    return re.sub(r"\[\[\s*(MORE|DOCUMENT)\s*\]\]", "", text or "").strip()


# ---------------------------------------------------------------------------------------------------- citations
# Act name patterns (ru + kk, lower case) → adilet code. The Civil Code's two parts are one group.
ACTS: dict[str, tuple[str, ...]] = {
    "K1500000414": (r"трудов\w*\s+кодекс", r"(?<!\w)тк(?!\w)", r"еңбек\s+кодекс", r"(?<!\w)ек(?!\w)"),
    "Z100000274_": (r"защит\w*\s+прав\s+потребител", r"(?<!\w)зпп(?!\w)", r"тұтынушылардың\s+құқықтарын\s+қорғау"),
    "K990000409_": (r"гражданск\w*\s+кодекс", r"(?<!\w)гк(?!\w)", r"азаматтық\s+кодекс", r"(?<!\w)ак(?!\w)"),
    "K1500000377": (r"гражданск\w*\s+процессуальн\w*\s+кодекс", r"(?<!\w)гпк(?!\w)", r"азаматтық\s+процест\w*\s+кодекс",
                    r"(?<!\w)апк(?!\w)"),
    "K2000000350": (r"административн\w*\s+процедурн", r"(?<!\w)аппк(?!\w)", r"әкімшілік\s+рәсімдік", r"әрпк"),
    "K1100000518": (r"семейн\w*\s+кодекс", r"о\s+браке(?:\s+\(супружестве\))?(?:\s+и\s+семье)?", r"брак\w*\s+\(супружеств", r"(?<!\w)кобс(?!\w)", r"неке\s+\(ерлі-зайыптылық\)",
                    r"неке\s+және\s+отбасы"),
    "K1400000235": (r"об\s+административных\s+правонарушени", r"(?<!\w)коап(?!\w)",
                    r"әкімшілік\s+құқық\s+бұзушылық", r"әқбтк"),
    "Z970000094_": (r"жилищных\s+отношени", r"тұрғын\s+үй\s+қатынастары"),
    "Z1600000486": (r"долев\w*\s+участи", r"үлестік\s+қатысу"),
    "K2500000214": (r"налогов\w*\s+кодекс", r"(?<!\w)нк(?!\w)", r"салық\s+кодекс"),
    "Z970000155_": (r"нотариат", ),
    "K2300000224": (r"социальн\w*\s+кодекс", r"әлеуметтік\s+кодекс"),
    "Z950002444_": (r"о\s+банках", r"банках\s+и\s+банковской", r"банктер\s+және\s+банк\s+қызметі"),
    "Z030000446_": (r"страховани\w*\s+гражданско-правовой\s+ответственности\s+владельцев",
                    r"(?<!\w)ог?пов?тс?(?!\w)", r"(?<!\w)осгпо(?!\w)", r"көлік\s+құралдары\s+иелерінің"),
    "K2000000360": (r"здоровье\s+народа", r"кодекс\w*\s+о\s+здоровь", r"халық\s+денсаулығы"),
    "Z1700000062": (r"коллекторск\w*\s+деятельност", r"коллекторлық\s+қызмет"),
    "Z1300000088": (r"государственных\s+(?:и\s+социально\s+ответственных\s+)?услуг",
                    r"мемлекеттік\s+(?:және\s+әлеуметтік\s+жауапкершілігі\s+бар\s+)?көрсетілетін\s+қызмет"),
    "K1400000226": (r"уголовн\w*\s+кодекс", r"(?<!\w)ук\s+рк(?!\w)", r"қылмыстық\s+кодекс", r"(?<!\w)қк(?!\w)"),
    "Z1200000056": (r"микрофинансов\w*\s+деятельност", r"микроқаржы\w*\s+қызмет"),
    "Z2200000178": (r"банкротств\w*\s+граждан", r"восстановлени\w*\s+платежеспособност", r"банкроттығы"),
    "Z1600000011": (r"о\s+платежах", r"төлемдер\s+және\s+төлем\s+жүйелері"),
    "Z2400000106": (r"государственных\s+закупк", r"мемлекеттік\s+сатып\s+алу"),
    "K1500000375": (r"предпринимательск\w*\s+кодекс", r"(?<!\w)пк\s+рк(?!\w)", r"кәсіпкерлік\s+кодекс"),
    "K950001000_": (r"конституци", r"ата\s+заң"),
}
GROUPS: dict[str, tuple[str, ...]] = {"K990000409_": ("K990000409_", "K940001000_"),
                                      "K940001000_": ("K990000409_", "K940001000_")}
ACT_RES = [(code, re.compile(p)) for code, ps in ACTS.items() for p in ps]
FOREIGN = re.compile(r"(?<!\w)рф(?!\w)|российской\s+федерации|ресей\s+федерациясы")
RU_REF = re.compile(r"(?i)\bст(?:атья|атьи|атье|атьей|атью|атьям|атьями|атьях)?\.?\s*(" + NUM + r")"
                    r"((?:\s*(?:,|и|или|–)\s*(?:ст\.?\s*)?" + NUM + r"(?!\s*(?:-?\s*ба[пб]|\.\d)))*)")
KK_REF = re.compile(r"(?i)(" + NUM + r")\s*-?\s*ба[пб]\w*")
EXTRA_NUM = re.compile(NUM)
# Codes Kazakhstan does not have (Russia does): «ст. 144 Жилищного кодекса РК» is an invented norm.
NONEXISTENT = re.compile(r"[\s\d.,п-]*(?:рк\s+)?жилищн\w*\s+кодекс")
UNKNOWN_ACT_AFTER = re.compile(r"[\s\d.,пч-]*(?:[^\W\d_]+\s+){0,3}?(?:кодекс|закон)")
NEAR_GAP = re.compile(r"[^\W\d_]*[»\")]*\s*\(?\s*(?:(?:ч\.|часть|особ\w*\.?|общ\w*\.?|ерекше|жалпы|бөлім|рк)[\s.,)]*)*")


def _low(s: str) -> str:
    return (s or "").lower().replace("ё", "е").replace(" ", " ").replace("\xa0", " ")


def act_at(text: str, start: int, end: int, kk_order: bool) -> str | None:
    """The act a reference at text[start:end] belongs to: the nearest act name after it (ru «ст. 113 ТК»), else the
    nearest before it (kk «Еңбек кодексінің 113-бабы» puts the act first)."""
    after = text[end:end + 60]
    after = re.split(r"(?<=[^\s.])\.\s+[А-ЯA-ZӘҒҚҢӨҰҮҺІ]|\n", after, maxsplit=1)[0]  # not into the next sentence
    before = text[max(0, start - 110):start]
    after_l, before_l = _low(after), _low(before)

    def first(seg: str) -> str | None:
        best = None
        for code, rx in ACT_RES:
            m = rx.search(seg)
            if m and (best is None or m.start() < best[0]):
                best = (m.start(), code)
        return best[1] if best else None

    def last(seg: str) -> str | None:
        best = None
        for code, rx in ACT_RES:
            for m in rx.finditer(seg):
                if best is None or m.start() > best[0]:
                    best = (m.start(), code)
        return best[1] if best else None

    code = re.search(r"\b([A-Z]\d{9,10}_?)\b", after)
    if code:
        return code.group(1)
    if FOREIGN.search(after_l[:40]):
        return "foreign"
    if NONEXISTENT.match(after_l):
        return "nonexistent"
    near = None  # «ЗПП ст. 30», «ГК ч. Особ. ст. 1070»: the act right before the reference
    for c, rx in ACT_RES:
        for m in rx.finditer(before_l):
            if NEAR_GAP.fullmatch(before_l[m.end():]) and (near is None or m.end() > near[0]):
                near = (m.end(), c)
    if near:
        return near[1]
    if kk_order:
        return last(before_l) or first(after_l)
    if first(after_l):
        return first(after_l)
    if UNKNOWN_ACT_AFTER.match(after_l):  # «ст. 5 Кодекса о …» we do not know: not the act mentioned before it
        return None
    return last(before_l[-40:])


@dataclass
class Cited:
    article: str
    code: str | None  # resolved act (adilet code), "foreign", or None when the act could not be told
    near: tuple[str, ...] = ()  # every act named within 150 characters (the parser may pick the wrong one)


def citations(answer: str) -> list[Cited]:
    out: list[Cited] = []
    for m in RU_REF.finditer(answer):
        nums = [m.group(1)] + EXTRA_NUM.findall(m.group(2) or "")
        code = act_at(answer, m.start(), m.end(), kk_order=False)
        near = tuple(sorted(acts_named(answer[max(0, m.start() - 150):m.end() + 150])))
        out += [Cited(n, code, near) for n in nums]
    for m in KK_REF.finditer(answer):
        near = tuple(sorted(acts_named(answer[max(0, m.start() - 150):m.end() + 150])))
        out.append(Cited(m.group(1), act_at(answer, m.start(), m.end(), kk_order=True), near))
    seen, uniq = set(), []
    for c in out:
        if (c.article, c.code) not in seen:
            seen.add((c.article, c.code))
            uniq.append(c)
    return uniq


def acts_named(answer: str) -> set[str]:
    low = _low(answer)
    return {code for code, rx in ACT_RES if rx.search(low)}


# ---------------------------------------------------------------------------------------------------- keyword classes
ADDRESSEES: dict[str, str] = {
    "seller": r"продав|магазин|исполнител|изготовител|сатушы|дүкен|орындаушы",
    "employer": r"работодател|жұмыс\s+беруші",
    "court": r"(?<!\w)суд(?!ь)|(?<!\w)сот(?:қа|та|ты|тың|\b)",
    "labor_inspection": r"инспекц\w*\s+(?:по\s+)?труд|трудов\w*\s+инспекц|инспектор\w*\s+(?:по\s+)?труд|еңбек\s+инспекц",
    "prosecutor": r"прокурат|прокурор",
    "akimat": r"акимат|(?<!\w)аким(?!\w)|әкімдік",
    "police": r"полици|(?<!\d)102(?!\d)",
    "bank": r"(?<!\w)банк",
    "regulator": r"агентств\w*[^.]{0,30}регулировани|аррфр|(?<!\w)арфр|национальн\w*\s+банк|нацбанк|қаржы\s+нарығын\s+реттеу",
    "consumer_body": r"(?:орган|департамент|комитет|инспекц)\w*[^.]{0,40}защит\w*\s+прав\s+потребител|"
                     r"тұтынушылардың\s+құқықтарын\s+қорғау[^.]{0,30}(?:орган|департамент|комитет)",
    "notary": r"нотариус|нотариал",
    "eotinish": r"e-?otinish|е-?өтініш|еотиниш",
    "egov_con": r"egov|эгов|электронн\w*\s+правительств|(?<!\w)цон(?!\w)|халыққа\s+қызмет\s+көрсету|госкорпораци",
    "insurer": r"страхов\w*\s+(?:компани|организаци)|страховщик|сақтандыру\s+(?:ұйым|компания)",
    "developer": r"застройщик|құрылыс\s+салушы",
    "osi_ksk": r"(?<!\w)оси(?!\w)|(?<!\w)кск(?!\w)|объединени\w*\s+собственник|пәтер\s+иелер|мүлік\s+иелерінің",
    "landlord": r"наймодател|арендодател|жалға\s+беруші",
    "utility": r"поставщик\w*\s+(?:коммунальн|услуг)|энергоснаб|водоканал|коммуналд|коммунальн\w*\s+служб",
    "lawyer": r"юрист|адвокат|заңгер",
    "emergency": r"(?<!\d)11[02](?!\d)|(?<!\d)10[13](?!\d)|скор\w*\s+помощ|экстренн|жедел\s+жәрдем|төтенше",
    "tax": r"налогов\w*\s+(?:орган|департамент|управлени)|государственн\w*\s+доход|мемлекеттік\s+кірістер|(?<!\w)кгд(?!\w)",
    "bailiff": r"судебн\w*\s+исполнител|частн\w*\s+судебн|сот\s+орындаушы",
    "mfo": r"(?<!\w)мфо(?!\w)|микрофинанс|микроқаржы",
    "collector": r"коллектор",
    "health": r"поликлиник|больниц|медицинск\w*\s+организац|фосмс|фонд\w*\s+социальн\w*\s+медицинск|клиник|емхана",
    "marketplace": r"маркетплейс|площадк|kaspi|каспи|wildberries|ozon",
    "conciliation": r"согласительн\w*\s+комисси|келісім\s+комиссия",
    "ombudsman": r"уполномоченн\w*\s+по\s+правам|омбудсмен",
    "registry": r"(?<!\w)загс|органы?\s+юстиции|регистрирующ|тіркеу\s+орган",
}
DOCUMENTS: dict[str, str] = {
    "claim": r"претенз|кінәрат|талап\s+хат",
    "complaint": r"жалоб|шағым(?!дан)",
    "lawsuit": r"исков\w*\s+заявлени|(?<!\w)иск(?:а|ом|у)?(?!\w)|талап\s+арыз|талап\s+қою",
    "application": r"заявлени|өтініш",
    "appeal": r"апелляц|обжалов|шағымдан|кассац",
    "notice": r"уведомлени|хабарлама",
    "power_of_attorney": r"доверенност|сенімхат",
    "receipt": r"расписк|қолхат",
    "agreement": r"соглашени|келісім\s*шарт|(?<!\w)договор",
    "request": r"запрос|ходатайств|сұрау\s+салу",
    "court_order": r"судебн\w*\s+приказ|сот\s+бұйрығы",
    "certificate": r"свидетельств|справк|анықтама|куәлік",
}
ADDR_RES = {k: re.compile(v) for k, v in ADDRESSEES.items()}
DOC_RES = {k: re.compile(v) for k, v in DOCUMENTS.items()}


def classes(text: str, table: dict[str, re.Pattern[str]]) -> set[str]:
    low = _low(text)
    return {k for k, rx in table.items() if rx.search(low)}


# ---------------------------------------------------------------------------------------------------- deadlines
WORDNUM = {
    "один": 1, "одного": 1, "одну": 1, "одна": 1, "двух": 2, "два": 2, "две": 2, "трех": 3, "три": 3, "четырех": 4,
    "четыре": 4, "пяти": 5, "пять": 5, "шести": 6, "шесть": 6, "семи": 7, "семь": 7, "десяти": 10, "десять": 10,
    "пятнадцати": 15, "пятнадцать": 15, "четырнадцати": 14, "четырнадцать": 14, "двадцати": 20, "двадцать": 20,
    "тридцати": 30, "тридцать": 30, "шестидесяти": 60, "шестьдесят": 60, "двенадцати": 12, "двенадцать": 12,
    "бір": 1, "екі": 2, "үш": 3, "төрт": 4, "бес": 5, "алты": 6, "жеті": 7, "он": 10, "жиырма": 20, "отыз": 30,
}
UNITS = [("hour", r"час|сағат"), ("day", r"дн[яейю]|день|сут(?:ок|ки)|күн|тәулік"),
         ("month", r"месяц|ай(?:дың|дан|ға|ы)?(?!\w)"), ("year", r"год|лет(?!\w)|жыл")]
DEADLINE_RE = re.compile(r"(?<![\d.\w])(\d{1,3}|" + "|".join(sorted(WORDNUM, key=len, reverse=True)) +
                         r")(?!\w)(?:\s*\(\w+\))?\s*(?:-|–)?\s*(?:[^\W\d_]+\s+){0,2}?(" +
                         "|".join(u for _, u in UNITS) + r")")


def deadlines(text: str) -> set[tuple[int, str, str]]:
    """(number, unit, kind) pairs: kind «work» for working days, «cal» otherwise."""
    out = set()
    low = _low(text)
    for m in DEADLINE_RE.finditer(low):
        raw = m.group(1)
        n = int(raw) if raw.isdigit() else WORDNUM.get(raw, 0)
        if not n:
            continue
        unit = next(u for u, rx in UNITS if re.match(rx, m.group(2)))
        kind = "work" if re.search(r"рабоч|жұмыс", low[m.start():m.end() + 12]) else "cal"
        out.add((n, unit, kind))
    if re.search(r"полугод|жарты\s+жыл", low):
        out.add((6, "month", "cal"))
    return out


def deadline_score(expected: str, answer: str) -> float | None:
    exp = deadlines(expected)
    if not exp:
        return None
    got = deadlines(answer)
    return sum(1 for e in exp if e in got) / len(exp)


# ---------------------------------------------------------------------------------------------------- other checks
KK_LETTERS = set("әғқңөұүһі")
ESCALATE = re.compile(r"юрист|адвокат|заңгер|(?<!\w)суд(?!ь)|(?<!\w)сот(?:қа|та|ты|тың|\b)|экстренн|(?<!\d)11[02](?!\d)|"
                      r"(?<!\d)10[123](?!\d)|скор\w*\s+помощ|полици|жедел\s+жәрдем")


def language_ok(answer: str, lang: str) -> bool:
    words = re.findall(r"[^\W\d_]{3,}", _low(answer))
    if not words:
        return False
    cyr = [w for w in words if re.search(r"[а-яәғқңөұүһі]", w)]
    if len(cyr) < 0.8 * len(words):
        return False
    kk = sum(1 for w in cyr if KK_LETTERS & set(w)) / len(cyr)
    return kk >= 0.15 if lang == "kk" else kk < 0.05


STOPWORDS = {"если", "чтобы", "либо", "наличии", "также", "есть", "этом", "этого", "или", "при"}


def _stems(text: str, n: int = 5) -> list[str]:
    return [w[:n] for w in re.findall(r"[^\W\d_]{4,}", _low(text)) if w not in STOPWORDS]


def include_score(elements: list[str], answer: str) -> float | None:
    if not elements:
        return None
    low = _low(answer)
    hit = 0
    for el in elements:
        st = _stems(el)
        if st and sum(1 for s in st if s in low) >= max(1, round(0.5 * len(st))):
            hit += 1
    return hit / len(elements)


MONTHS = ["январ", "феврал", "март", "апрел", "ма[йя]", "июн", "июл", "август", "сентябр", "октябр", "ноябр", "декабр"]


def fact_found(value: Any, answer: str) -> bool:
    low = _low(answer)
    digits = re.sub(r"(?<=\d)[\s \xa0](?=\d)", "", low)
    v = str(value).strip()
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", v)
    if m:
        y, mo, d = m.groups()
        pats = [re.escape(f"{d}.{mo}"), re.escape(f"{int(d)}.{mo}"), re.escape(v),
                rf"(?<!\d){int(d)}\s+{MONTHS[int(mo) - 1]}"]
        return any(re.search(p, digits) for p in pats)
    if re.fullmatch(r"[\d\s.,]+", v):
        return re.sub(r"\D", "", v) in digits
    st = _stems(v, 5) or [_low(v)]
    return sum(1 for s in st if s in low) >= max(1, round(0.6 * len(st)))


def facts_score(facts: dict[str, Any], answer: str) -> float | None:
    vals = [v for v in facts.values() if v not in (None, "", [])]
    if not vals:
        return None
    return sum(1 for v in vals if fact_found(v, answer)) / len(vals)


# ---------------------------------------------------------------------------------------------------- scoring
COMPONENTS = ("norm", "addressee", "document", "deadline", "include", "facts", "escalation", "language")


def score(answer: str, item: Item, corpus: Corpus | None = None) -> dict[str, Any]:
    """Deterministic scores of one answer (each 0..1 or None when not applicable) and the invented norms."""
    cited = citations(answer)
    named = acts_named(answer)
    comp: dict[str, float | None] = dict.fromkeys(COMPONENTS)
    if item.must_cite:
        parts = []
        for nm in item.must_cite:
            group = GROUPS.get(nm.code, (nm.code,))
            if any(c.article == nm.article and (c.code in group or (c.code is None and set(group) & named))
                   for c in cited):
                parts.append(1.0)
            elif set(group) & named:
                parts.append(1 / 3)
            else:
                parts.append(0.0)
        comp["norm"] = sum(parts) / len(parts)
    exp = item.expected or {}
    if item.type in ("routing", "refusal") and exp.get("addressee"):
        want = classes(exp["addressee"], ADDR_RES)
        if want:
            comp["addressee"] = len(want & classes(answer, ADDR_RES)) / len(want)
    if item.type in ("routing", "drafting_check") and exp.get("document"):
        want = classes(exp["document"], DOC_RES)
        if want:
            comp["document"] = len(want & classes(answer, DOC_RES)) / len(want)
    if item.type in ("deadline", "routing") and exp.get("deadline"):
        comp["deadline"] = deadline_score(exp["deadline"], answer)
    if item.type == "drafting_check":
        comp["include"] = include_score(list(exp.get("must_include") or []), answer)
    if item.type == "extraction":
        comp["facts"] = facts_score(item.facts, answer)
    if exp.get("escalate_to_lawyer"):
        comp["escalation"] = 1.0 if ESCALATE.search(_low(answer)) else 0.0
    comp["language"] = 1.0 if language_ok(answer, item.lang) else 0.0

    invented = []
    for c in cited:
        if c.code == "foreign":
            invented.append({"article": c.article, "code": c.code, "why": "foreign_law"})
        elif c.code == "nonexistent":
            invented.append({"article": c.article, "code": c.code, "why": "nonexistent_act"})
        elif (corpus is not None and c.code and c.code in ACTS
              and any(g in corpus.acts for g in GROUPS.get(c.code, (c.code,)))
              and not any(corpus.exists(a, c.article) for a in {c.code, *c.near})):
            invented.append({"article": c.article, "code": c.code, "why": "not_in_corpus"})
    if not any(i["why"] == "foreign_law" for i in invented) and re.search(
            r"(?:закон|кодекс)\w*[^.]{0,40}(?<!\w)(?:рф(?!\w)|российской\s+федерации)", _low(answer)):
        invented.append({"article": "", "code": "foreign", "why": "foreign_law"})
    if item.type == "extraction":  # an IIN/BIN that is not in the client's text
        for num in re.findall(r"(?<!\d)\d{12}(?!\d)", re.sub(r"(?<=\d)\s(?=\d)", "", answer)):
            if num not in re.sub(r"\s", "", item.question):
                invented.append({"article": "", "code": num, "why": "invented_id"})
    vals = [v for v in comp.values() if v is not None]
    auto = 0.0 if invented else (sum(vals) / len(vals) if vals else 0.0)
    return {"cited": [{"article": c.article, "code": c.code} for c in cited], "components": comp,
            "invented": invented, "auto": round(auto, 4),
            "unchecked_refs": sum(1 for c in cited if not c.code)}


# ---------------------------------------------------------------------------------------------------- judge
JUDGE_SYSTEM = (
    "Ты — строгий проверяющий юридических ответов по праву Республики Казахстан. Тебе дают вопрос клиента, эталонный "
    "ответ юриста, список «красных флагов» (ошибок, которых ответ не должен допускать) и ответ модели. Оцени ТОЛЬКО "
    "ответ модели. Верни один JSON без пояснений вокруг: {\"red_flags\": [номера нарушенных флагов, с 1], "
    "\"invented\": true|false, \"why\": \"одна короткая фраза\"}. invented = true, только если ответ уверенно называет "
    "норму (статью, закон), срок, сумму или орган, которые противоречат эталону или явно не существуют; общие слова и "
    "отсутствие нормы — не выдумка. Флаг нарушен, только если ответ действительно делает то, что флаг запрещает.")


def judge_messages(item: Item, answer: str) -> list[dict[str, str]]:
    flags = "\n".join(f"{i}. {f}" for i, f in enumerate(item.red_flags, 1)) or "(нет)"
    exp = item.expected or {}
    ref = exp.get("answer") or ""
    for k, label in (("addressee", "Адресат"), ("document", "Документ"), ("deadline", "Срок")):
        if exp.get(k):
            ref += f"\n{label}: {exp[k]}"
    if item.unverified:
        ref += "\nНе сверено (не штрафовать за расхождение): " + "; ".join(item.unverified)
    user = f"ВОПРОС:\n{item.question}\n\nЭТАЛОН:\n{ref}\n\nКРАСНЫЕ ФЛАГИ:\n{flags}\n\nОТВЕТ МОДЕЛИ:\n{answer[:4000]}"
    return [{"role": "system", "content": JUDGE_SYSTEM}, {"role": "user", "content": user}]


def parse_judge(text: str, n_flags: int) -> dict[str, Any] | None:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    flags = sorted({int(x) for x in d.get("red_flags") or [] if str(x).isdigit() and 1 <= int(x) <= n_flags})
    return {"red_flags": flags, "invented": bool(d.get("invented")), "why": str(d.get("why") or "")[:300]}


# ---------------------------------------------------------------------------------------------------- run
class RawFile:
    """Raw answers, one JSON line each, appended as they come (an interrupted run keeps what it did)."""

    def __init__(self, path: Path):
        self.path, self._lock = path, threading.Lock()
        path.parent.mkdir(parents=True, exist_ok=True)

    def rows(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [json.loads(x) for x in self.path.read_text("utf-8").splitlines() if x.strip()]

    def append(self, row: dict[str, Any]) -> None:
        with self._lock, self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def rewrite(self, rows: list[dict[str, Any]]) -> None:
        with self._lock:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
            tmp.replace(self.path)


def latest(rows: list[dict[str, Any]]) -> dict[tuple[str, str, str], dict[str, Any]]:
    """The last row per (model, mode, id): a re-run of failed calls supersedes them."""
    out: dict[tuple[str, str, str], dict[str, Any]] = {}
    for r in rows:
        out[(r["model"], r["mode"], r["id"])] = r
    return out


def run(items: list[Item], models: list[str], modes: list[str], model: Model, corpus: Corpus | None, raw: RawFile,
        workers: int = 6, log: Callable[[str], None] = print) -> None:
    done = {k for k, r in latest(raw.rows()).items() if not r.get("error")}
    retrieved: dict[str, tuple[list[Any], float]] = {}
    if "rag" in modes and corpus is not None:
        for it in items:
            t0 = time.perf_counter()
            hits = corpus.retrieve(it.question, it.lang)
            retrieved[it.id] = (hits, round((time.perf_counter() - t0) * 1000, 1))
    for name in models:
        for mode in modes:
            if mode == "rag" and corpus is None:
                continue
            todo = [it for it in items if (name, mode, it.id) not in done]
            unavailable = threading.Event()

            def one(it: Item, name: str = name, mode: str = mode, unavailable: threading.Event = unavailable) -> None:
                if unavailable.is_set():
                    return
                row: dict[str, Any] = {"id": it.id, "lang": it.lang, "type": it.type, "category": it.category,
                                       "difficulty": it.difficulty, "verified": it.verified, "model": name, "mode": mode}
                hits = None
                if mode == "rag":
                    hits, ms = retrieved[it.id]
                    row["retrieved"] = [{"code": h.code, "article": h.number} for h in hits]
                    row["retrieval_hit"] = any(any(h.code in GROUPS.get(n.code, (n.code,)) and h.number == n.article
                                                   for h in hits) for n in it.must_cite) if it.must_cite else None
                    row["retrieval_ms"] = ms
                t0 = time.perf_counter()
                try:
                    answer = clean_answer(model(name, messages_for(it, hits)))
                    wall = time.perf_counter() - t0
                    own = model.last_latency() if hasattr(model, "last_latency") else None
                    row.update(answer=answer, latency=round(own if own is not None else wall, 2),
                               wall=round(wall, 2), error=None)
                    row.update(score(answer, it, corpus))
                    if not answer:
                        row["error"] = "empty answer"
                except ModelUnavailable as e:
                    unavailable.set()
                    log(f"  {name}: not served by the catalog ({str(e)[:80]}), skipped")
                    return
                except Exception as e:  # noqa: BLE001 — one failed call must not stop the run
                    row.update(error=f"{type(e).__name__}: {e}"[:300], answer="",
                               latency=round(time.perf_counter() - t0, 2))
                raw.append(row)

            t_mode = time.perf_counter()
            with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
                list(pool.map(one, todo))
            rows = [r for k, r in latest(raw.rows()).items() if k[0] == name and k[1] == mode]
            ok = [r for r in rows if not r.get("error")]
            log(f"  {name} [{mode}]: {len(ok)}/{len(items)} answered, auto {mean([r['auto'] for r in ok]):.3f} "
                f"({time.perf_counter() - t_mode:.0f} s)")


def judge(items: list[Item], judge_model: str, model: Model, raw: RawFile, workers: int = 6,
          log: Callable[[str], None] = print) -> None:
    by_id = {it.id: it for it in items}
    rows = list(latest(raw.rows()).values())
    todo = [r for r in rows if not r.get("error") and r.get("answer") and r["id"] in by_id
            and (r.get("judge") or {}).get("model") != judge_model]
    lock = threading.Lock()
    n = [0]

    def one(r: dict[str, Any]) -> None:
        it = by_id[r["id"]]
        out = None
        try:
            out = parse_judge(model(judge_model, judge_messages(it, r["answer"])), len(it.red_flags))
        except Exception as e:  # noqa: BLE001
            r["judge_error"] = f"{type(e).__name__}: {e}"[:200]
        if out is not None:
            r["judge"] = {"model": judge_model, **out}
        with lock:
            n[0] += 1
            if n[0] % 100 == 0:
                log(f"  judge: {n[0]}/{len(todo)}")
                raw.rewrite(rows)

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        list(pool.map(one, todo))
    raw.rewrite(rows)
    log(f"  judge {judge_model}: {sum(1 for r in todo if r.get('judge'))}/{len(todo)} judged")


# ---------------------------------------------------------------------------------------------------- report
def mean(xs: list[float]) -> float:
    return statistics.mean(xs) if xs else 0.0


def with_judge(r: dict[str, Any]) -> float | None:
    j = r.get("judge")
    if not j:
        return None
    return 0.0 if (j["red_flags"] or j["invented"]) else r["auto"]


def _pc(x: float | None) -> str:
    return "—" if x is None else f"{100 * x:.0f}"


def _pct(x: float | None) -> str:
    return "—" if x is None else f"{100 * x:.0f} %"


def _p(values: list[float], q: float) -> str:
    if not values:
        return "—"
    v = sorted(values)
    return f"{v[min(len(v) - 1, int(q * len(v)))]:.1f}"


def summary(rs: list[dict[str, Any]]) -> dict[str, Any]:
    ok = [r for r in rs if not r.get("error")]
    comp = {c: [r["components"][c] for r in ok if r["components"].get(c) is not None] for c in COMPONENTS}
    judged = [r for r in ok if r.get("judge")]
    lat = [r["latency"] for r in ok if r.get("latency") is not None]
    rag = [r for r in rs if r.get("retrieval_hit") is not None]
    return {
        "n": len(rs), "answered": len(ok), "auto": mean([r["auto"] for r in ok]) if ok else None,
        "judge": mean([with_judge(r) for r in judged]) if judged else None, "judged": len(judged),
        **{c: (mean(v) if v else None) for c, v in comp.items()},
        "invented": mean([1.0 if r["invented"] else 0.0 for r in ok]) if ok else None,
        "j_invented": mean([1.0 if r["judge"]["invented"] else 0.0 for r in judged]) if judged else None,
        "j_flags": mean([1.0 if r["judge"]["red_flags"] else 0.0 for r in judged]) if judged else None,
        "p50": _p(lat, 0.5), "p95": _p(lat, 0.95),
        "retrieval": mean([1.0 if r["retrieval_hit"] else 0.0 for r in rag]) if rag else None,
    }


def report_tables(rows: list[dict[str, Any]], items: list[Item]) -> str:
    ids = {it.id for it in items}
    rows = [r for r in latest(rows).values() if r["id"] in ids]
    keys = sorted({(r["model"], r["mode"]) for r in rows}, key=lambda k: (k[0], k[1] != "norag"))
    label = {"norag": "без поиска", "rag": "с поиском"}
    L: list[str] = []
    L += ["### Итог", "",
          "| Модель | Режим | Ответов | **Итог, авто** | Итог с судьёй (LLM) | Норма | Адресат | Документ | Срок | "
          "Язык | Выдуманные нормы, авто | Выдумка, судья (LLM) | Красные флаги, судья (LLM) | p50 / p95, с |",
          "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for m, mode in keys:
        s = summary([r for r in rows if r["model"] == m and r["mode"] == mode])
        L.append(f"| {m} | {label[mode]} | {s['answered']}/{s['n']} | **{_pc(s['auto'])}** | {_pc(s['judge'])} | "
                 f"{_pc(s['norm'])} | {_pc(s['addressee'])} | {_pc(s['document'])} | {_pc(s['deadline'])} | "
                 f"{_pc(s['language'])} | {_pct(s['invented'])} | {_pct(s['j_invented'])} | {_pct(s['j_flags'])} | "
                 f"{s['p50']} / {s['p95']} |")

    def by(field_: str, title: str, values: list[Any], fmt: Callable[[Any], str] = str) -> None:
        attr = {"lang": "lang"}.get(field_, field_)
        L.extend(["", f"### {title}", "", "Итог, авто / с судьёй (LLM), %.", "",
                  "| Модель | Режим | " + " | ".join(f"{fmt(v)} (n={sum(1 for it in items if getattr(it, attr) == v)})"
                                                    for v in values) + " |",
                  "|---|---|" + "---:|" * len(values)])
        for m, mode in keys:
            cells = []
            for v in values:
                s = summary([r for r in rows if r["model"] == m and r["mode"] == mode and r.get(field_) == v])
                cells.append(_pc(s["auto"]) + (f" / {_pc(s['judge'])}" if s["judge"] is not None else ""))
            L.append(f"| {m} | {label[mode]} | " + " | ".join(cells) + " |")

    by("category", "По категориям", sorted({it.category for it in items}))
    by("type", "По типам вопросов", ["norm", "deadline", "routing", "refusal", "drafting_check", "extraction"])
    by("lang", "По языкам", ["ru", "kk"])
    by("difficulty", "По сложности", [1, 2, 3])
    by("verified", "Сверено с официальным текстом (`verified`)", [True, False], fmt=lambda v: "да" if v else "нет")
    rag = [k for k in keys if k[1] == "rag"]
    if rag:
        s = summary([r for r in rows if r["model"] == rag[0][0] and r["mode"] == "rag"])
        L += ["", f"Поиск нашёл хотя бы одну статью из `must_cite` в топ-{RAG_ARTICLES}: **{_pc(s['retrieval'])} %** "
                  f"вопросов с нормой."]
    errors = [r for r in rows if r.get("error")]
    if errors:
        L += ["", f"Ошибок вызова / пустых ответов: {len(errors)} (в итог не входят; подробно — в сыром JSONL)."]
    return "\n".join(L) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--bench", type=Path, help="Zann-Bench JSONL (only split=open is read)")
    ap.add_argument("--models", default=",".join(DEFAULT_MODELS), help="comma-separated catalog model ids")
    ap.add_argument("--mode", choices=("both", "rag", "norag"), default="both")
    ap.add_argument("--index-db", default=os.environ.get("ZANN_INDEX_DB", ""),
                    help="database URL with zann_articles (RAG and the invented-norm check)")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--rpm", type=int, default=MAX_RPM, help=f"requests per minute, at most {MAX_RPM}")
    ap.add_argument("--workers", type=int, default=6, help="parallel calls (all share the limiter)")
    ap.add_argument("--max-tokens", type=int, default=1200)
    ap.add_argument("--date", default=date.today().isoformat())
    ap.add_argument("--raw", type=Path, help="raw answers JSONL (default data/zann/bench-<date>.jsonl)")
    ap.add_argument("--tables", type=Path, help="markdown tables (default data/zann/bench-<date>-tables.md)")
    ap.add_argument("--judge", help="catalog model id of the LLM judge: judge the raw answers")
    ap.add_argument("--report-only", action="store_true", help="only rescore the raw answers and write the tables")
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
    items = load_bench(a.bench)
    items = items[: a.limit] if a.limit else items
    raw = RawFile(a.raw or REPO / "data" / "zann" / f"bench-{a.date}.jsonl")
    corpus = Corpus(a.index_db) if a.index_db else None
    model: Model
    if a.dry_run:
        model = FakeModel()
    elif not key and not a.report_only:
        print("NVIDIA_API_KEY is not set (or use --dry-run)", file=sys.stderr)
        return 2
    elif a.report_only:
        model = FakeModel()  # not called
    else:
        model = NvidiaCatalog(key, limiter, max_tokens=a.max_tokens)
    if a.judge:
        jm = model if a.dry_run else NvidiaCatalog(key, limiter, max_tokens=400, temperature=0.0)
        judge(items, a.judge, jm, raw, workers=a.workers)
    elif a.report_only:
        by_id = {it.id: it for it in items}
        rows = raw.rows()
        for r in rows:  # rescore with the current rules (the judge's verdicts are kept)
            if not r.get("error") and r["id"] in by_id:
                r.update(score(r.get("answer") or "", by_id[r["id"]], corpus))
        raw.rewrite(rows)
    else:
        modes = ["norag", "rag"] if a.mode == "both" else [a.mode]
        models = ["fake/dry-run"] if a.dry_run else [m.strip() for m in a.models.split(",") if m.strip()]
        print(f"{len(items)} open questions × {len(models)} models × {modes}; ≤ {limiter.rpm} requests/min")
        run(items, models, modes, model, corpus, raw, workers=a.workers)
    out = a.tables or REPO / "data" / "zann" / f"bench-{a.date}-tables.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report_tables(raw.rows(), items), encoding="utf-8")
    print(f"tables: {out}\nraw:    {raw.path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
