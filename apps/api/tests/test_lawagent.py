"""The legal agent: tools over the official portal, and the check that keeps only norms it actually read."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from konsilier.lawagent.agent import LawAgent
from konsilier.lawagent.sources import Adilet, ActNotFound, act_code, page_text, split_articles

FIX = Path(__file__).parent / "fixtures" / "adilet"
TK = "K1500000414"
Q113 = "При прекращении трудового договора выплата сумм, причитающихся работнику от работодателя, производится не позднее трех рабочих дней после его прекращения."


def fake_fetch(url: str) -> str:
    code = url.rstrip("/").split("/")[-1]
    p = FIX / f"{code}.txt"
    if not p.exists():
        raise ActNotFound(url)
    return p.read_text("utf-8")


def test_article_is_cut_from_the_official_page():
    a = Adilet(fetch=fake_fetch)
    art = a.article(f"https://adilet.zan.kz/rus/docs/{TK}", "Статья 113")
    assert art.act_title == "Трудовой кодекс Республики Казахстан"
    assert art.title == "Порядок и сроки выплаты заработной платы"
    assert Q113 in art.text and "Статья 114" not in art.text
    assert art.url == f"https://old.adilet.zan.kz/rus/docs/{TK}"
    title, items = a.contents(TK)
    assert ("113", "Порядок и сроки выплаты заработной платы") in items
    with pytest.raises(ActNotFound):
        a.article(TK, "999")
    with pytest.raises(ActNotFound):
        act_code("not a code")


def test_html_pages_are_parsed_too():
    raw = ("<html><head><title>Закон - ИПС \"Әділет\"</title><script>x()</script></head><body>"
           "<p><b>Статья 1. Первая</b></p><p>1. Текст&nbsp;первой.</p><p><b>Статья 2. Вторая</b></p><p>Текст второй.</p>"
           "</body></html>")
    title, text = page_text(raw)
    arts = split_articles(text)
    assert title == "Закон" and arts["1"] == ("Первая", "1. Текст первой.") and arts["2"][0] == "Вторая"


def test_kazakh_headings():
    arts = split_articles("**113-бап. Жалақы төлеу тәртібі**\n1. Мәтін.\n**114-бап. Келесі**\nМәтін.")
    assert arts["113"] == ("Жалақы төлеу тәртібі", "1. Мәтін.")


# ------------------------------------------------------------------ the agent loop with a scripted model
def tool_use(id_, name, inp):
    return NS(type="tool_use", id=id_, name=name, input=inp)


def text(t):
    return NS(type="text", text=t)


def resp(stop, *content):
    return NS(stop_reason=stop, content=list(content), usage=NS(input_tokens=100, output_tokens=20))


class ScriptedClient:
    def __init__(self, turns):
        self.turns, self.calls = list(turns), []
        self.messages = self

    def create(self, **kw):
        self.calls.append(kw)
        return self.turns.pop(0)


def run(final_norms, extra_turns=()):
    turns = [
        resp("tool_use", tool_use("t1", "act_contents", {"act": TK})),
        resp("tool_use", tool_use("t2", "get_article", {"act": TK, "article": "113"}),
             tool_use("t3", "deadline", {"start": "2026-09-25", "business_days": 3})),
        *extra_turns,
        resp("end_turn", text(json.dumps({"answer": "Работодатель должен рассчитаться за 3 рабочих дня.",
                                          "steps": ["Напишите требование работодателю."],
                                          "norms": final_norms, "confidence": "high"}, ensure_ascii=False))),
    ]
    client = ScriptedClient(turns)
    pack = NS(add_days=lambda start, cal, bus: date(2026, 9, 30))
    agent = LawAgent(client, "claude-sonnet-5", Adilet(fetch=fake_fetch))
    res = agent.ask("Уволили, не рассчитались", context={"pack": pack, "forums": [], "case": {}},
                    language="ru", country="Казахстан")
    return res, client


def test_verified_norm_is_kept_with_official_link():
    res, client = run([{"act_code": TK, "article": "Статья 113", "quote": Q113}])
    assert res.needs_lawyer is False and res.unverified == 0
    assert res.norms[0]["url"].endswith(TK) and res.norms[0]["article"] == "113"
    # the deadline tool result went back to the model (computed by code, not by the model)
    results = [c for m in client.calls[-1]["messages"] if m["role"] == "user" and isinstance(m["content"], list)
               for c in m["content"] if isinstance(c, dict) and c.get("type") == "tool_result"]
    assert any(r["content"] == "2026-09-30" for r in results)
    # web search is restricted to the official portal
    ws = next(t for t in client.calls[0]["tools"] if t.get("name") == "web_search")
    assert ws["allowed_domains"] == ["adilet.zan.kz"]


def test_invented_or_unread_norms_are_dropped_and_flagged():
    res, _ = run([
        {"act_code": TK, "article": "113", "quote": "Работодатель обязан выплатить двойную зарплату за каждый день."},
        {"act_code": TK, "article": "114", "quote": "Что-то из статьи, которую агент не открывал в этом запуске."},
        {"act_code": "K9999999999", "article": "1", "quote": "Несуществующий кодекс, выдуманная статья и цитата."},
    ])
    assert res.norms == [] and res.unverified == 3 and res.needs_lawyer is True


# ------------------------------------------------------------------ API
def test_ask_endpoint_stores_verified_answer_and_redacts(ctx):
    from .test_e2e import web_user

    turns = [
        resp("tool_use", tool_use("t1", "get_article", {"act": TK, "article": "113"})),
        resp("end_turn", text(json.dumps({"answer": "Расчёт — не позднее трёх рабочих дней.", "steps": [],
                                          "norms": [{"act_code": TK, "article": "113", "quote": Q113}],
                                          "confidence": "high"}, ensure_ascii=False))),
    ]
    client = ScriptedClient(turns)
    ctx.container.law_agent = LawAgent(client, "claude-sonnet-5", Adilet(fetch=fake_fetch))
    api = web_user(ctx)
    cid = api.post("/v1/cases", expect=201, json={"text": "Меня уволили и не рассчитались, зарплата 300000",
                                                  "country": "KZ"})["case"]["id"]
    out = api.post(f"/v1/cases/{cid}/questions", expect=201, json={"question": "В какой срок должны рассчитаться?"})
    assert out["needs_lawyer"] is False and out["norms"][0]["article"] == "113"
    assert api.get(f"/v1/cases/{cid}/questions").json()[0]["id"] == out["id"]
    other = web_user(ctx)
    assert ctx.client.post(f"/v1/cases/{cid}/questions", headers=other.h, json={"question": "чужое дело?"}).status_code == 404


def test_ask_without_agent_is_503(ctx):
    from .test_e2e import web_user

    ctx.container.law_agent = None
    api = web_user(ctx)
    cid = api.post("/v1/cases", expect=201, json={"text": "Меня уволили и не рассчитались", "country": "KZ"})["case"]["id"]
    r = ctx.client.post(f"/v1/cases/{cid}/questions", headers=api.h, json={"question": "Какой срок расчёта?"})
    assert r.status_code == 503
