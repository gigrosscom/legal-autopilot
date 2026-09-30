"""Timing harness for the first chat answer: home page → /start → case → streamed reply.

Runs the real API code (FastAPI app, case engine, chat agent, chain client, adilet parser, Zann corpus lookup) on a
throw-away SQLite database. Only the outside world is simulated, with latencies measured on production (30.09.2026):

- the case engine's model (classification + field extraction): QUALIFY_S per call (Claude Haiku, ≈2 s; 2 calls ≈ 4.2 s);
- the chat providers: time to the first byte of a round (TTFT) and the pace of the tokens; Gemini SIM_GEMINI_TTFT,
  Cerebras SIM_CEREBRAS_TTFT; ``busy`` adds GEMINI_BUSY_S before Gemini's first byte (429 → pause → retry / next model);
- the live adilet page: LIVE_S.

The simulated model looks the article up before writing (what production shows: first words ≈5–6 s) unless the
system prompt tells it to write the short answer before any tool call — then it writes first and looks up after.

    cd apps/api && python3 scripts/chat_timing.py            # every scenario, a table of timings
    SIM_RUNS=3 python3 scripts/chat_timing.py

Timings: ``create`` = POST /v1/cases; ``first words`` = from the moment the person pressed «Send» on /start (triage
+ case + chat request) to the first text event; ``chat ttft`` = from the chat request to the first text event.
"""

from __future__ import annotations

import gzip
import json
import logging
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace as NS
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from konsilier.config import Settings  # noqa: E402
from konsilier.container import build_container  # noqa: E402
from konsilier.core.llm.mock import HeuristicMockProvider  # noqa: E402
from konsilier.core.models import Base  # noqa: E402
from konsilier.gemini import Block, Message, Usage  # noqa: E402
from konsilier.main import create_app  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
QUALIFY_S = float(os.environ.get("QUALIFY_S", "2.0"))
LIVE_S = float(os.environ.get("LIVE_S", "1.5"))
GEMINI_TTFT = float(os.environ.get("SIM_GEMINI_TTFT", "1.6"))
CEREBRAS_TTFT = float(os.environ.get("SIM_CEREBRAS_TTFT", "0.5"))
GEMINI_BUSY_S = float(os.environ.get("GEMINI_BUSY_S", "3.0"))
CHUNK_S = 0.015  # between streamed chunks
RUNS = int(os.environ.get("SIM_RUNS", "2"))
STORY = "Вернуть деньги за бракованный товар"
ARTICLE = "30"
ANSWER_FIRST = "before calling any tool"  # the phrase of the chat prompt that makes the model write first
# SIM_TOOL_FIRST=1: the model ignores that instruction and still looks the article up before writing (worst case)
TOOL_FIRST = os.environ.get("SIM_TOOL_FIRST") == "1"


class SlowLLM:
    """The case engine's model: the heuristic mock behind a network-like pause."""

    def __init__(self) -> None:
        self.inner = HeuristicMockProvider()

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self.inner, name)
        if not callable(attr):
            return attr

        def call(*a: Any, **k: Any) -> Any:
            time.sleep(QUALIFY_S)
            return attr(*a, **k)
        return call


class _SimStream:
    def __init__(self, client: "SimClient", kw: dict[str, Any]):
        self.client, self.kw, self._final = client, kw, None
        self.attempts: list[dict[str, Any]] = []

    def __enter__(self) -> "_SimStream":
        return self

    def __exit__(self, *a: Any) -> bool:
        return False

    def close(self) -> None:
        pass

    @property
    def text_stream(self):
        c, kw = self.client, self.kw
        time.sleep(c.ttft + (GEMINI_BUSY_S if c.busy else 0))
        last = kw["messages"][-1]["content"]
        after_tool = isinstance(last, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in last)
        tools = {t.get("name") for t in kw.get("tools") or []}
        blocks: list[Block] = []
        if after_tool or "get_article" not in tools:
            text = ("Продавец обязан вернуть деньги за товар с недостатком. **Напишите продавцу претензию.**\n[[MORE]]\n"
                    "1. Сохраните чек. 2. Напишите претензию. 3. Если откажут — жалоба. [[DOCUMENT]]")
            stop = "end_turn"
        elif ANSWER_FIRST in kw["system"] and not TOOL_FIRST:
            text = "Продавец обязан вернуть деньги за бракованный товар. **Напишите продавцу претензию.**\n[[MORE]]\n"
            stop = "tool_use"
        else:
            text, stop = "", "tool_use"
        words = text.split(" ") if text else []
        for i, w in enumerate(words):
            if i:
                time.sleep(CHUNK_S)
            yield w + (" " if i < len(words) - 1 else "")
        if text:
            blocks.append(Block("text", text=text))
        if stop == "tool_use":
            time.sleep(0.3)  # the arguments of the call are generated
            act = kw["system"].split("Main acts on the official portal (code — title):\n", 1)[-1].split(" — ", 1)[0]
            blocks.append(Block("tool_use", id=f"t{time.monotonic_ns()}", name="get_article",
                                input={"act": act.strip(), "article": ARTICLE}))
        self._final = Message(blocks, stop, Usage(3000, len(words)))

    def get_final_message(self) -> Message:
        if self._final is None:
            for _ in self.text_stream:
                pass
        return self._final


class SimClient:
    def __init__(self, name: str, ttft: float, busy: bool = False):
        self.name, self.ttft, self.busy = name, ttft, busy
        self.messages = self

    def stream(self, **kw: Any) -> _SimStream:
        kw.pop("prefer", None)
        return _SimStream(self, kw)

    def warm(self) -> None:
        pass


def page(code: str) -> str:
    return (f"<html><head><title>Закон о защите прав потребителей - ИПС \"Әділет\"</title></head><body><article>"
            f"<p>Статья {ARTICLE}. Права потребителя при продаже товара ненадлежащего качества</p>"
            "<p>1. Потребитель вправе потребовать возврата уплаченной суммы.</p>"
            "<p>Статья 31. Сроки</p><p>Текст.</p></article></body></html>")


def live_fetch(url: str) -> str:
    time.sleep(LIVE_S)
    return page(url.rsplit("/", 1)[-1])


def build(tmp: Path, chain: list[SimClient], local_corpus: bool) -> NS:
    settings = Settings(database_url=f"sqlite:///{tmp}/t.db", packs_dir=REPO / "packs", storage_backend="local",
                        storage_local_dir=tmp / "files", llm_provider="mock", soffice_bin="", admin_token="adm",
                        bot_api_secret="bot", scheduler_interval_seconds=0, smtp_host=None, payment_mode="stub",
                        background_jobs="thread", official_search_enabled=False)
    container = build_container(settings, llm=SlowLLM())
    Base.metadata.drop_all(container.engine_db)
    Base.metadata.create_all(container.engine_db)
    from konsilier.chat import ChatAgent
    from konsilier.lawagent.sources import Adilet
    from konsilier.openai_compat import ChainClient

    local = None
    if local_corpus:
        try:
            from konsilier.zann.corpus import CorpusTexts, file_key
        except ImportError:  # the code before the local lookup
            CorpusTexts = None
        if CorpusTexts is not None:
            from konsilier.core.models import ZannFile

            pack = container.packs.pack("KZ")
            codes = {a.code for s in pack.manifest.legal_sources for a in s.key_acts}
            with container.session_factory() as s:
                for code in codes:
                    from konsilier.zann.corpus import extract_act

                    title, text = extract_act(page(code))
                    container.storage.put(file_key(code, "ru"), gzip.compress(text.encode()), "application/gzip")
                    s.add(ZannFile(code=code, lang="ru", key=file_key(code, "ru"), url="u", title=title,
                                   sha256="x", chars=len(text), bytes=0))
                s.commit()
            local = CorpusTexts(container.session_factory, container.storage)
    adilet = Adilet(fetch=live_fetch, local=local) if local is not None else Adilet(fetch=live_fetch)
    kw = {"web_search": False}
    container.chat_agent = ChatAgent(ChainClient(chain, **({"first_token_timeout": 1.5}
                                                           if "first_token_timeout" in ChainClient.__init__.__code__.co_varnames
                                                           else {})),
                                     "gemini-3.1-flash-lite", adilet, **kw)
    app = create_app(settings, container, start_scheduler=False)
    return NS(app=app, container=container)


class Probe:
    """Wraps the chat agent: the moment the first text event leaves it."""

    def __init__(self, agent: Any):
        self.agent, self.first = agent, None

    def __getattr__(self, name: str) -> Any:
        return getattr(self.agent, name)

    def stream(self, *a: Any, **k: Any):
        for ev in self.agent.stream(*a, **k):
            if ev["type"] == "text" and self.first is None:
                self.first = time.perf_counter()
            yield ev


def one_run(chain: list[SimClient], local_corpus: bool) -> dict[str, float]:
    with tempfile.TemporaryDirectory() as d:
        env = build(Path(d), chain, local_corpus)
        with TestClient(env.app) as client:
            token = client.post("/v1/users", json={"language": "ru"}).json()["token"]
            h = {"Authorization": f"Bearer {token}"}
            probe = Probe(env.container.chat_agent)
            env.container.chat_agent = probe
            client.get("/v1/chat/info")  # the chat page opens (connection warm-up where there is one)
            t0 = time.perf_counter()
            client.post("/v1/triage", json={"text": STORY, "country": "KZ", "language": "ru"})
            r = client.post("/v1/cases", headers=h, json={"text": STORY, "language": "ru", "country": "KZ",
                                                          "accept_terms": True, "defer": True})
            assert r.status_code == 201, r.text
            t_case = time.perf_counter()
            cid = r.json()["case"]["id"]
            t_chat = time.perf_counter()
            r = client.post(f"/v1/cases/{cid}/chat", headers=h, json={"text": STORY, "language": "ru"})
            t_end = time.perf_counter()
            events = [json.loads(x[6:]) for x in r.text.splitlines() if x.startswith("data: ")]
            done = events[-1]
            assert done["type"] == "done", events[-3:]
            first = probe.first or t_end
            time.sleep(QUALIFY_S * 2 + 0.5)  # let a deferred classification finish before the database goes away
            return {"create": t_case - t0, "first_words": first - t0, "chat_ttft": first - t_chat,
                    "total": t_end - t0, "offer": float(bool(done["message"].get("offer_document")))}


SCENARIOS = {
    "gemini first (prod order), Gemini healthy": lambda: [SimClient("gemini", GEMINI_TTFT),
                                                          SimClient("cerebras", CEREBRAS_TTFT)],
    "gemini first, Gemini busy (429 → retry)": lambda: [SimClient("gemini", GEMINI_TTFT, busy=True),
                                                        SimClient("cerebras", CEREBRAS_TTFT)],
    "cerebras first": lambda: [SimClient("cerebras", CEREBRAS_TTFT), SimClient("gemini", GEMINI_TTFT)],
}


def main() -> None:
    logging.basicConfig(level=os.environ.get("LOG", "WARNING"))
    print(f"QUALIFY_S={QUALIFY_S} LIVE_S={LIVE_S} gemini ttft={GEMINI_TTFT} (+{GEMINI_BUSY_S} busy) "
          f"cerebras ttft={CEREBRAS_TTFT} runs={RUNS} tool_first={TOOL_FIRST}")
    print(f"{'scenario':46} {'create':>7} {'first words':>12} {'chat ttft':>10} {'total':>7} {'offer':>6}")
    for name, chain in SCENARIOS.items():
        runs = [one_run(chain(), local_corpus=True) for _ in range(RUNS)]
        med = {k: statistics.median(r[k] for r in runs) for k in runs[0]}
        print(f"{name:46} {med['create']:7.2f} {med['first_words']:12.2f} {med['chat_ttft']:10.2f} "
              f"{med['total']:7.2f} {'yes' if med['offer'] else 'no':>6}")


if __name__ == "__main__":
    main()
