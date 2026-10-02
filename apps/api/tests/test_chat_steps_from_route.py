"""PM 02.10 (prod @ba41b36, flooding, 450 000 ₸, act of the КСК): the solution floated between runs — 19:51 «претензия
→ суд», 20:50 «документы для суда → иск → экспертиза» under a card «Досудебная претензия». The steps of a solution come
from the case's route (routes.yaml, checked by ZANN: ГПК ст. 152 ч. 1 пп. 1 — no compulsory claim for a tort, ст. 29 —
the defendant's court; R-31 — the claim with the person's sum first), the same source as the card."""

from __future__ import annotations

from konsilier.api.chat import route_steps_text

from .test_chat import _claude, _sse
from .test_e2e import web_user

FLOOD = ("Сосед сверху затопил мою квартиру в Алматы 20.09.2026, ущерб ~450000 тенге, есть акт от КСК. "
         "Отказывается возмещать. Что делать?")
DRIFT = ("Что делать:\n1. **Подготовьте документы для суда.**\n2. **Подайте иск.**\n3. **Заявите ходатайство о "
         "судебной экспертизе.**\n[[MORE]]\n**Почему суд.** Сосед отвечает за вред, причинённый имуществу.")


def _reply(ctx, text):
    api = web_user(ctx)
    cid = api.post("/v1/cases", expect=201, json={"text": FLOOD, "country": "KZ"})["case"]["id"]
    ctx.container.chat_agent, ctx.container.chat_fallback_agent = _claude(text), None
    ev = _sse(ctx.client.post(f"/v1/cases/{cid}/chat", headers=api.h, json={"text": FLOOD}))
    return ev[-1]["message"]["text"], api.get(f"/v1/cases/{cid}").json()


def test_flood_steps_are_the_route_not_the_model(ctx):
    for _ in range(3):  # the same steps every time, whatever the model wrote
        text, case = _reply(ctx, DRIFT)
        short = text.split("[[MORE]]")[0]
        assert short.startswith("Что делать:\n1. **Тот, кто причинил ущерб, — претензия**.")
        assert "2. **Районный (городской) суд — иск** — если не возместил." in short
        assert "Подготовьте документы для суда" not in text
        assert "**Почему суд.** Сосед отвечает за вред" in text  # the model's details stay
        assert [r["label"] for r in case["recipients"]][0].endswith("претензия")


def test_a_question_is_not_replaced(ctx):
    text, _ = _reply(ctx, "Когда это случилось и есть ли акт?")
    assert text.startswith("Когда это случилось")


def test_steps_text_shape():
    route = [{"step": 1, "label": "Продавец — претензия", "when": None},
             {"step": 2, "label": "Департамент — жалоба", "when": "если отказали."}]
    assert route_steps_text(route, "kk").startswith("Не істеу керек:\n1. **Продавец — претензия**.")
    assert route_steps_text(route, "ru").endswith("2. **Департамент — жалоба** — если отказали.")
    assert route_steps_text([], "ru") == ""
