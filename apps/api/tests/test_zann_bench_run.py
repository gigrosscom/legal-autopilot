"""Zann-Bench runner (tools/zann/bench_run.py): only open items are ever loaded (hidden ones never reach a prompt,
the raw file or the report), the ≤40 requests/min limiter, the NVIDIA client's retries, the per-type scoring
(norm citations, addressee / document, deadline, invented norms), the judge's parsing, and a dry run end to end —
no network, no key. The law texts here are the invented fixtures of test_zann_search, not the real law."""

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

SECRET = "СЕКРЕТНЫЙ-ВОПРОС-ЭКЗАМЕНА"


def line(id_, split="open", **kw):
    d = {"id": id_, "split": split, "task": "qa", "type": "norm", "category": "labor", "country": "KZ",
         "language": "ru", "question": "Уволили, не выплатили расчёт при увольнении. Что делать?",
         "expected": {"addressee": "работодатель", "document": "претензия", "deadline": "3 рабочих дня",
                      "answer": "Расчёт — не позднее трёх рабочих дней (ТК ст. 113).", "escalate_to_lawyer": False},
         "must_cite": [{"act": "Трудовой кодекс РК", "article": "ст. 113 п. 1",
                        "url": f"https://old.adilet.zan.kz/rus/docs/{TK}"}],
         "red_flags": ["называет срок 10 дней"], "difficulty": 1, "verified": True, "unverified": [],
         "verified_by": None, "facts": {}, "topic": "dismissal", "route": "labor.dismissal"}
    d.update(kw)
    return d


LINES = [
    line("t-1"),
    line("t-2", language="kk", question="Жұмыстан босатылған кезде төлеу тәртібі қандай?"),
    line("t-h1", split="hidden", question=SECRET),
    line("t-3", type="routing", category="consumer", question="Можно ли вернуть товар надлежащего качества?",
         expected={"addressee": "продавец (магазин)", "document": "заявление (претензия) о возврате товара",
                   "deadline": "14 календарных дней", "answer": "Да (ЗПП ст. 9).", "escalate_to_lawyer": False},
         must_cite=[{"act": "ЗПП", "article": "ст. 9", "url": f"https://old.adilet.zan.kz/rus/docs/{ZPP}"}]),
    {**line("t-h2", question=SECRET), "split": None},  # unmarked counts as hidden too
]


@pytest.fixture
def bench(tmp_path):
    p = tmp_path / "kz-v1.jsonl"
    p.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in LINES), encoding="utf-8")
    return p


def test_hidden_items_are_never_loaded(bench):
    items = br.load_bench(bench)
    assert [i.id for i in items] == ["t-1", "t-2", "t-3"]
    assert all(SECRET not in i.question for i in items)
    assert [d["id"] for d in br.open_items(bench)] == ["t-1", "t-2", "t-3"]
    assert items[0].must_cite[0].code == TK and items[0].must_cite[0].article == "113"


def test_hidden_items_never_reach_a_prompt_the_raw_file_or_the_report(bench, tmp_path, monkeypatch):
    fake = br.FakeModel()
    monkeypatch.setattr(br, "FakeModel", lambda: fake)
    raw, tables = tmp_path / "raw.jsonl", tmp_path / "t.md"
    assert br.main(["--bench", str(bench), "--dry-run", "--mode", "norag", "--raw", str(raw),
                    "--tables", str(tables)]) == 0
    assert br.main(["--bench", str(bench), "--dry-run", "--judge", "judge/fake", "--raw", str(raw),
                    "--tables", str(tables)]) == 0
    prompts = json.dumps(fake.seen, ensure_ascii=False)
    assert len(fake.seen) == 6 and SECRET not in prompts and "t-h" not in prompts
    assert SECRET not in raw.read_text() and "t-h1" not in raw.read_text() and "t-h2" not in raw.read_text()
    assert SECRET not in tables.read_text()


def test_bench_format_is_checked(tmp_path):
    bad = tmp_path / "bad.jsonl"
    bad.write_text(json.dumps({"id": "x", "split": "open", "language": "ru", "question": "?"}) + "\n")
    with pytest.raises(ValueError, match="type"):
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
            return httpx.Response(404, text='{"detail": "Not found"}')
        if body["model"] == "gone/model":
            return httpx.Response(410, text="Gone")
        if len(seen) == 1:
            return httpx.Response(429, headers={"Retry-After": "1"})
        return httpx.Response(200, json={"choices": [{"message": {"content": "<think>…</think>Ответ: ст. 113 ТК"}}]})

    slept = []
    cat = br.NvidiaCatalog("k", br.RateLimiter(40, sleep=lambda s: None),
                           client=httpx.Client(transport=httpx.MockTransport(handler)), sleep=slept.append)
    assert cat("meta/llama-3.2-90b-vision-instruct", [{"role": "user", "content": "?"}]) == "Ответ: ст. 113 ТК"
    assert slept == [1.0] and seen[0].headers["Authorization"] == "Bearer k"
    assert seen[0].url == "https://integrate.api.nvidia.com/v1/chat/completions"
    for m in ("nope/model", "gone/model"):
        with pytest.raises(br.ModelUnavailable):
            cat(m, [{"role": "user", "content": "?"}])


def test_citations_resolve_the_act_in_both_word_orders():
    def refs(t):
        return {(c.article, c.code) for c in br.citations(t)}

    assert ("113", TK) in refs("Работодатель обязан выплатить всё по ст. 113 ТК РК.")
    assert ("30", ZPP) in refs("ЗПП ст. 30 п. 1; ст. 14 Трудового кодекса")
    assert ("14", TK) in refs("ЗПП ст. 30 п. 1; ст. 14 Трудового кодекса")
    assert ("113", TK) in refs("Еңбек кодексінің 113-бабы бойынша төленеді.")
    assert ("1070", "K990000409_") in refs("(ГК ч. Особ. ст. 1070 п. 1)")
    assert ("15", ZPP) in refs("статьи 15 и 17 Закона «О защите прав потребителей»")
    assert ("17", ZPP) in refs("статьи 15 и 17 Закона «О защите прав потребителей»")
    assert ("18", ZPP) in refs("согласно Закону «О защите прав потребителей» (статья 18), продавец")
    assert ("144", "nonexistent") in refs("ст. 153–156 ГПК РК и ст. 144 Жилищного кодекса РК")
    assert ("156", "K1500000377") in refs("ст. 153–156 ГПК РК и ст. 144 Жилищного кодекса РК")
    assert ("5", None) in refs("ст. 5 ГК РК и ст. 5 Кодекса о недрах")
    assert ("18", "foreign") in refs("по ст. 18 Закона РФ о защите прав потребителей")


def _items(tmp_path):
    p = tmp_path / "b.jsonl"
    p.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in LINES), encoding="utf-8")
    return {i.id: i for i in br.load_bench(p)}


def test_norm_deadline_routing_and_invented(corpus, tmp_path):  # noqa: F811
    sf, storage = corpus
    Indexer(sf, storage).run()
    c = br.Corpus(str(sf.kw["bind"].url.render_as_string(hide_password=False)))
    it = _items(tmp_path)
    ok = br.score("Расчёт — не позднее трёх рабочих дней (ст. 113 ТК РК).", it["t-1"], c)
    assert ok["components"]["norm"] == 1.0 and not ok["invented"] and ok["components"]["language"] == 1.0
    act_only = br.score("Это регулирует Трудовой кодекс.", it["t-1"], c)
    assert abs(act_only["components"]["norm"] - 1 / 3) < 1e-9
    bad = br.score("Смотрите ст. 9999 Трудового кодекса.", it["t-1"], c)
    assert bad["invented"][0]["why"] == "not_in_corpus" and bad["auto"] == 0.0
    kk = br.score("Еңбек кодексінің 113-бабы бойынша үш жұмыс күні ішінде төленеді.", it["t-2"], c)
    assert kk["components"]["norm"] == 1.0 and kk["components"]["language"] == 1.0
    assert br.score("Ст. 113 ТК: всё выплачивается.", it["t-2"], c)["components"]["language"] == 0.0  # not kk
    r = br.score("Да, верните продавцу в магазин в течение 14 календарных дней, напишите заявление-претензию "
                 "(ст. 9 Закона «О защите прав потребителей»).", it["t-3"], c)
    assert r["components"]["addressee"] == 1.0 and r["components"]["document"] == 1.0
    assert r["components"]["deadline"] == 1.0 and r["components"]["norm"] == 1.0 and r["auto"] == 1.0
    wrong = br.score("Обратитесь в суд в течение 7 дней.", it["t-3"], c)
    assert wrong["components"]["addressee"] == 0.0 and wrong["components"]["deadline"] == 0.0
    assert br.deadline_score("3 рабочих дня", "не позднее трёх рабочих дней") == 1.0
    assert br.deadline_score("3 рабочих дня", "в течение 3 календарных дней") == 0.0


def test_judge_output_is_parsed_strictly():
    assert br.parse_judge('ok {"red_flags": [2, 9, "x"], "invented": true, "why": "срок"} end', 3) == {
        "red_flags": [2], "invented": True, "why": "срок"}
    assert br.parse_judge("no json", 2) is None


def test_dry_run_end_to_end_with_rag_and_corpus_check(bench, corpus, tmp_path):  # noqa: F811
    sf, storage = corpus
    Indexer(sf, storage).run()
    url = str(sf.kw["bind"].url.render_as_string(hide_password=False))
    tables, raw = tmp_path / "t.md", tmp_path / "raw.jsonl"
    assert br.main(["--bench", str(bench), "--dry-run", "--index-db", url, "--tables", str(tables),
                    "--raw", str(raw), "--date", "2026-10-01"]) == 0
    rows = [json.loads(x) for x in raw.read_text().splitlines()]
    assert len(rows) == 6 and {r["mode"] for r in rows} == {"rag", "norag"}
    norag = [r for r in rows if r["mode"] == "norag"]
    assert all(r["invented"] and r["invented"][0]["why"] == "not_in_corpus" for r in norag)  # «ст. 9999»
    rag = {r["id"]: r for r in rows if r["mode"] == "rag"}
    assert rag["t-1"]["retrieval_hit"] and rag["t-1"]["components"]["norm"] == 1.0
    md = tables.read_text()
    assert "| fake/dry-run | без поиска | 3/3 | **0** |" in md and "### По категориям" in md
    # a re-run does not repeat answered questions
    assert br.main(["--bench", str(bench), "--dry-run", "--index-db", url, "--tables", str(tables),
                    "--raw", str(raw)]) == 0
    assert len(raw.read_text().splitlines()) == 6


def test_without_key_it_refuses_politely(bench, monkeypatch, capsys):
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    assert br.main(["--bench", str(bench)]) == 2
    assert "NVIDIA_API_KEY" in capsys.readouterr().err
