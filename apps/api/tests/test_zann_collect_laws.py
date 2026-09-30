"""Zann corpus collector (tools/zann/collect_laws.py): parsing, language check and manifest — no network."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import httpx
import pytest

from konsilier.lawagent.sources import ActNotFound

REPO = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location("collect_laws", REPO / "tools" / "zann" / "collect_laws.py")
cl = importlib.util.module_from_spec(_spec)
sys.modules["collect_laws"] = cl  # dataclasses look the module up while the file loads
_spec.loader.exec_module(cl)

BODY_RU = "<p>Статья 1. Основные понятия</p><p>&nbsp;&nbsp;Настоящий Закон регулирует отношения.</p>" * 10
BODY_KK = "<p>1-бап. Негізгі ұғымдар</p><p>Осы Заң қоғамдық қатынастарды реттейді, құқықтарын қорғау.</p>" * 10


def page(title: str, body: str) -> str:
    return (f"<html><head><title>{title}</title><script>var x=1;</script></head><body>"
            f"<div id='menu'>Главная Поиск Меню портала</div><article>{body}</article>"
            f"<div id='footer'>© ИЗПИ реклама</div></body></html>")


PAGES = {
    "https://old.adilet.zan.kz/rus/docs/Z1700000062": page('О коллекторской деятельности - ИПС &quot;Әділет&quot;', BODY_RU),
    "https://old.adilet.zan.kz/kaz/docs/Z1700000062": page('Коллекторлық қызмет туралы - "Әділет" АҚЖ', BODY_KK),
    # the portal answers, but the Kazakh page holds the Russian text: not saved as kk
    "https://old.adilet.zan.kz/kaz/docs/K1500000414": page("Трудовой кодекс", BODY_RU),
    "https://old.adilet.zan.kz/rus/docs/K1500000414": page("Трудовой кодекс Республики Казахстан - ИПС", BODY_RU),
}


def fake_fetch(url: str) -> str:
    if url not in PAGES:
        raise ActNotFound(url)
    return PAGES[url]


def test_extract_act_keeps_only_the_document_body_and_clean_titles():
    title, text = cl.extract_act(PAGES["https://old.adilet.zan.kz/rus/docs/Z1700000062"])
    assert title == "О коллекторской деятельности"
    assert text.startswith("Статья 1. Основные понятия\n")
    assert "Настоящий Закон регулирует отношения." in text
    assert "Меню портала" not in text and "реклама" not in text and "var x" not in text
    assert "\xa0" not in text and "\n\n\n" not in text
    kk_title, kk_text = cl.extract_act(PAGES["https://old.adilet.zan.kz/kaz/docs/Z1700000062"])
    assert kk_title == "Коллекторлық қызмет туралы"
    assert cl.looks_kazakh(kk_text) and not cl.looks_kazakh(text)
    assert cl.extract_act("<html><body><p>нет статьи</p></body></html>")[1] == ""


def test_codes_from_packs_takes_adilet_links_most_cited_first(tmp_path):
    (tmp_path / "a.yaml").write_text("url: https://adilet.zan.kz/rus/docs/K1500000414\n"
                                     "x: https://old.adilet.zan.kz/kaz/docs/Z100000274_ ", "utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.md").write_text("[ТК](https://adilet.zan.kz/rus/docs/K1500000414) K9 not a link", "utf-8")
    assert cl.codes_from_packs(tmp_path) == ["K1500000414", "Z100000274_"]
    assert "K2000000350" in cl.codes_from_packs(REPO / "packs" / "kz")  # the real pack cites the Admin Offences Code


def test_validate_codes_rejects_junk_and_bulk():
    assert cl.validate_codes(["K1500000414", " K1500000414", "Z100000274_"]) == ["K1500000414", "Z100000274_"]
    with pytest.raises(SystemExit):
        cl.validate_codes(["DROP TABLE"])
    with pytest.raises(SystemExit):
        cl.validate_codes([f"K{n:010d}" for n in range(cl.MAX_CODES + 1)])


def test_collect_writes_texts_and_a_deduplicated_manifest(tmp_path):
    out, manifest, logs = tmp_path / "corpus", tmp_path / "manifest.jsonl", []
    stats = cl.collect(["Z1700000062", "K1500000414", "Z999999999_"], ["ru", "kk"], out, manifest, fake_fetch,
                       log=logs.append)
    assert stats == {"saved": 3, "skipped": 0, "missing": 3, "failed": 0}
    assert sorted(p.name for p in out.iterdir()) == ["K1500000414.ru.txt", "Z1700000062.kk.txt", "Z1700000062.ru.txt"]
    rows = [json.loads(line) for line in manifest.read_text("utf-8").splitlines()]
    assert [(r["code"], r["lang"]) for r in rows] == [("K1500000414", "ru"), ("Z1700000062", "kk"), ("Z1700000062", "ru")]
    ru = next(r for r in rows if r["code"] == "Z1700000062" and r["lang"] == "ru")
    text = (out / "Z1700000062.ru.txt").read_text("utf-8")
    assert set(ru) == {"code", "title", "lang", "url", "fetched_at", "sha256", "chars"}
    assert ru["sha256"] == hashlib.sha256(text.encode()).hexdigest() and ru["chars"] == len(text)
    assert ru["url"] == "https://old.adilet.zan.kz/rus/docs/Z1700000062" and ru["title"] == "О коллекторской деятельности"
    assert any("K1500000414 kk: no text in this language" in m for m in logs)

    # a re-run skips what is on disk; --force refetches without duplicating manifest rows
    assert cl.collect(["Z1700000062"], ["ru", "kk"], out, manifest, fake_fetch, log=logs.append)["skipped"] == 2
    cl.collect(["Z1700000062"], ["ru"], out, manifest, fake_fetch, force=True, log=logs.append)
    assert len(manifest.read_text("utf-8").splitlines()) == 3


def test_polite_fetcher_retries_on_429_and_5xx_then_gives_up():
    calls, sleeps = [], []
    answers = iter([429, 503, 200])

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        code = next(answers)
        return httpx.Response(code, text="ok" if code == 200 else "busy", headers={"Retry-After": "7"} if code == 429 else {})

    client = httpx.Client(transport=httpx.MockTransport(handler), headers={"User-Agent": cl.USER_AGENT})
    f = cl.PoliteFetcher(delay=1.0, retries=3, sleep=sleeps.append, client=client)
    assert f("https://old.adilet.zan.kz/rus/docs/K1500000414") == "ok"
    assert len(calls) == 3 and 7.0 in sleeps
    assert calls[0].headers["User-Agent"].startswith("Konsilier.AI Zann")

    always_down = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    with pytest.raises(httpx.HTTPStatusError):
        cl.PoliteFetcher(retries=1, sleep=lambda s: None, client=always_down)("https://old.adilet.zan.kz/x")
    gone = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(404)))
    with pytest.raises(ActNotFound):
        cl.PoliteFetcher(sleep=lambda s: None, client=gone)("https://old.adilet.zan.kz/x")
