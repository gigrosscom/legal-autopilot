"""Zann-Bench runner (tools/zann/bench_run.py): bench format, the ≤40 requests/min limiter, the NVIDIA client's
retries, citation scoring (correct, wrong act, not in the corpus), and a dry run end to end — no network, no key.
The law texts here are the invented fixtures of test_zann_search, not the real law."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import httpx
import pytest

from konsilier.zann.index import Indexer

from .test_zann_search import TK, ZPP, corpus, db  # noqa: F401 — fixtures

REPO = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location("bench_run", REPO / "tools" / "zann" / "bench_run.py")
br = importlib.util.module_from_spec(_spec)
sys.modules["bench_run"] = br
_spec.loader.exec_module(br)

LINES = [
    {"id": "t-ru-1", "lang": "ru", "question": "Уволили, не выплатили расчёт при увольнении. Что делать?",
     "reference_answer": "Все суммы при увольнении выплачиваются не позднее трех рабочих дней.", "act": TK,
     "article": "113", "act_title": "Трудовой кодекс Республики Казахстан", "verified_by": None},
    {"id": "t-kk-1", "lang": "kk", "question": "Жұмыстан босатылған кезде төлеу тәртібі қандай?",
     "reference_answer": "Барлық сомалар үш жұмыс күнінен кешіктірілмей төленеді.", "act": TK, "article": "113",
     "act_title": "Қазақстан Республикасының Еңбек кодексі", "verified_by": "Юрист"},
    {"id": "t-ru-2", "lang": "ru", "question": "Можно ли вернуть товар надлежащего качества?",
     "reference_answer": "Да, в течение четырнадцати дней.", "act": ZPP, "article": "9",
     "accept": [[ZPP, "30"]]},
]


@pytest.fixture
def bench(tmp_path):
    p = tmp_path / "kz-v1.jsonl"
    p.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in LINES), encoding="utf-8")
    return p


def test_bench_format_is_checked(bench, tmp_path):
    items = br.load_bench(bench)
    assert [i.id for i in items] == ["t-ru-1", "t-kk-1", "t-ru-2"] and items[2].accept == [[ZPP, "30"]]
    bad = tmp_path / "bad.jsonl"
    bad.write_text(json.dumps({"id": "x", "lang": "ru", "question": "?"}) + "\n")
    with pytest.raises(ValueError, match="reference_answer"):
        br.load_bench(bad)


def test_limiter_never_exceeds_40_a_minute():
    now = [0.0]
    slept = []

    def sleep(s):
        slept.append(s)
        now[0] += s

    lim = br.RateLimiter(100, clock=lambda: now[0], sleep=sleep)
    assert lim.rpm == 40  # the free tier's cap even if more is asked
    for _ in range(40):
        lim.wait()
    assert not slept
    lim.wait()  # the 41st call waits for the first to leave the window
    assert slept and 59 < now[0] <= 61
    calls = list(lim.calls)
    assert all(calls[i + 40] - calls[i] >= 60 for i in range(len(calls) - 40))


def test_nvidia_client_retries_429_and_reports_unknown_models():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        body = json.loads(request.content)
        if body["model"] == "nope/model":
            return httpx.Response(404, text='{"detail": "model not found"}')
        if len(seen) == 1:
            return httpx.Response(429, headers={"Retry-After": "1"})
        return httpx.Response(200, json={"choices": [{"message": {"content": "<think>…</think>Ответ: ст. 113 ТК"}}]})

    slept = []
    cat = br.NvidiaCatalog("k", br.RateLimiter(40, sleep=lambda s: None),
                           client=httpx.Client(transport=httpx.MockTransport(handler)), sleep=slept.append)
    assert cat("meta/llama-3.3-70b-instruct", [{"role": "user", "content": "?"}]) == "Ответ: ст. 113 ТК"
    assert slept == [1.0] and seen[0].headers["Authorization"] == "Bearer k"
    assert seen[0].url == "https://integrate.api.nvidia.com/v1/chat/completions"
    with pytest.raises(br.ModelUnavailable):
        cat("nope/model", [{"role": "user", "content": "?"}])


def test_citations_and_scores():
    item = br.Item(**LINES[0])
    ok = br.score("Работодатель обязан выплатить всё по ст. 113 ТК РК.", item)
    assert ok["correct_citation"] and not ok["invented"]
    wrong = br.score("Это ст. 113 Гражданского кодекса.", item)
    assert not wrong["correct_citation"] and wrong["invented"][0]["why"] == "wrong_act"
    kk = br.Item(**LINES[1])
    assert br.score("Еңбек кодексінің 113-бабы бойынша төленеді.", kk)["correct_citation"]
    by_code = br.score("См. статья 113 (K1500000414).", item)
    assert by_code["correct_citation"]
    assert br.overlap("выплачиваются не позднее трех рабочих дней", item.reference_answer) > 0.5
    assert br.overlap("", item.reference_answer) == 0.0
    accepted = br.score("Смотрите ст. 30 Закона о защите прав потребителей.", br.Item(**{**LINES[2], "act_title":
                                                                                         "О защите прав потребителей"}))
    assert accepted["correct_citation"]


def test_dry_run_end_to_end_with_rag_and_corpus_check(bench, corpus, tmp_path):  # noqa: F811
    sf, storage = corpus
    Indexer(sf, storage).run()
    url = str(sf.kw["bind"].url.render_as_string(hide_password=False))
    report, raw = tmp_path / "report.md", tmp_path / "raw.jsonl"
    assert br.main(["--bench", str(bench), "--dry-run", "--index-db", url, "--report", str(report),
                    "--raw", str(raw), "--date", "2026-10-01"]) == 0
    rows = [json.loads(x) for x in raw.read_text().splitlines()]
    assert len(rows) == 6 and {r["mode"] for r in rows} == {"rag", "norag"}
    rag = {r["id"]: r for r in rows if r["mode"] == "rag"}
    assert rag["t-ru-1"]["correct_citation"] and rag["t-ru-1"]["retrieval_hit"]
    assert rag["t-kk-1"]["correct_citation"]
    norag = [r for r in rows if r["mode"] == "norag"]
    assert not any(r["correct_citation"] for r in norag)
    assert norag[0]["invented"][0]["why"] == "not_in_corpus"  # «ст. 999 Трудового кодекса» does not exist
    md = report.read_text()
    assert "# Zann-Bench — 2026-10-01" in md and "фальшивой моделью" in md
    assert "| fake/dry-run | rag | 3/3 |" in md and "| fake/dry-run | norag | 3/3 | 0 % |" in md
    assert "## По языкам" in md and "проверено юристом: 1" in md


def test_without_key_it_refuses_politely(bench, monkeypatch, capsys):
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    assert br.main(["--bench", str(bench)]) == 2
    assert "NVIDIA_API_KEY" in capsys.readouterr().err
