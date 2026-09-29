"""Bot tests: screen rendering + the API client against the real FastAPI app (in-process)."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "bot"))
sys.path.insert(0, str(ROOT / "apps" / "api"))

from konsilier_bot.api import KonsilierApi  # noqa: E402
from konsilier_bot.ui import case_screen  # noqa: E402


def _case(**kw):
    base = {"id": "c1", "language": "ru", "status": "intake", "actions": [], "proposal": None, "question": None,
            "status_label": "x", "ai_label": "AI"}
    base.update(kw)
    return base


def test_intake_screen_shows_question_and_skip_for_optional():
    s = case_screen(_case(question={"field": "seller_bin", "text": "БИН?", "optional": True}))
    assert s.text == "БИН?" and s.buttons == [[("Пропустить", "skip:c1")]]


def test_ready_document_screen():
    action = {"id": "a1", "approval_status": "approved", "instructions": ["Шаг один"], "email_allowed": True,
              "addressee": {"email": "shop@example.com"}, "title": "Претензия", "has_pdf": True,
              "action_id": "claim"}
    s = case_screen(_case(status="action_ready", actions=[action]))
    assert s.document_action is action
    assert "1. Шаг один" in s.text
    assert [b[1] for b in s.buttons[0]] == ["sub:c1", "mail:c1"]


def test_pending_approval_hides_document():
    action = {"id": "a1", "approval_status": "pending", "instructions": []}
    s = case_screen(_case(status="action_ready", actions=[action]))
    assert s.document_action is None and "проверку юристом" in s.text


def test_clarify_offers_response_classes():
    action = {"id": "a1", "deadline": None}
    s = case_screen(_case(status="awaiting_response", actions=[action],
                          proposal={"type": "clarify", "message": "Уточните"}))
    callbacks = [b[1] for row in s.buttons for b in row]
    assert callbacks == ["cls:c1:full", "cls:c1:partial", "cls:c1:refusal", "cls:c1:none"]
    assert all(len(c.encode()) <= 64 for c in callbacks)


@pytest.fixture
def api_app(tmp_path):
    from fastapi import FastAPI

    from konsilier.config import Settings
    from konsilier.container import build_container
    from konsilier.core.documents import NullPdfConverter
    from konsilier.core.llm.mock import HeuristicMockProvider
    from konsilier.core.models import Base
    from konsilier.main import create_app

    settings = Settings(database_url=f"sqlite:///{tmp_path}/bot.db", packs_dir=ROOT / "packs",
                        storage_local_dir=tmp_path / "files", bot_api_secret="s", approval_required_first_n=0,
                        soffice_bin="", payment_mode="stub")
    container = build_container(settings, llm=HeuristicMockProvider(), pdf=NullPdfConverter())
    Base.metadata.create_all(container.engine_db)
    app: FastAPI = create_app(settings, container, start_scheduler=False)
    return app


def test_client_drives_a_case(api_app):
    async def scenario():
        api = KonsilierApi("http://api", "s", transport=httpx.ASGITransport(app=api_app))
        out = await api.create_case("42", "Займ в МФО оформили мошенники 01.09.2026 на 50000, я не брал")
        cid = out["case"]["id"]
        assert out["case"]["scenario"]["id"] == "kz.money.credit_fraud"
        assert (await api.active_case("42"))["id"] == cid
        # answer by field, not by position: the interview order is scenario data and may change
        answers = {"lender_name": "МФО Ромашка", "applicant_name": "Иванов Иван", "applicant_iin": "900101300123",
                   "applicant_phone": "+77010000000", "applicant_address": "Алматы, ул. Абая 1",
                   "loan_date": "2026-09-01", "amount": "150000",
                   "problem_description": "Узнал из кредитной истории о займе, который не оформлял"}
        question = out["reply"]["question"]
        for _ in range(20):
            if question is None:
                break
            out = await api.message("42", cid, answers.get(question["field"], "пропустить"))
            question = out["reply"]["question"]
        assert out["case"]["status"] == "qualified"
        out = await api.prepare_next("42", cid)
        action = out["case"]["actions"][0]
        doc = await api.document("42", cid, action["id"], "docx")
        assert doc[:2] == b"PK"
        out = await api.submitted("42", cid, action["id"])
        out = await api.response("42", cid, action["id"], no_response=True)
        assert out["proposal"]["action_id"] == "complaint_arrf"
        screen = case_screen(out["case"])
        assert ("Подготовить документ", f"prep:{cid}") in screen.buttons[0]
        await api.close()

    asyncio.run(scenario())


def test_universal_case_shows_forum_choice_then_acknowledgement():
    from konsilier_bot.ui import case_screen

    base = {"id": "c1", "language": "ru", "status": "intake", "scenario": None, "actions": [], "proposal": None,
            "question": None}
    choose = case_screen({**base, "coverage": {"options": [{"id": "kz.police", "name": "Полиция"},
                                                           {"id": "kz.prosecutor", "name": "Прокуратура"}]}})
    assert [row[0][1] for row in choose.buttons] == ["forum:c1:0", "forum:c1:1"]
    ack = case_screen({**base, "scenario": {"id": "x"}, "coverage": {"options": []},
                       "safety": {"pending_ack": "false_report"}})
    assert ack.buttons == [[("Понимаю и подтверждаю", "ack:c1:false_report")]]


def test_profile_texts_fit_telegram_limits():
    from konsilier_bot.i18n import t
    from konsilier_bot.main import BOT_COMMANDS

    for lang in ("ru", "kk"):
        assert len(t("profile.short", lang)) <= 120
        assert len(t("profile.description", lang).strip()) <= 512
        for c in BOT_COMMANDS:
            assert 0 < len(t(f"profile.commands.{c}", lang)) <= 256
            assert t(f"profile.commands.{c}", lang) != f"profile.commands.{c}"


def test_unpaid_document_shows_transfer_details_and_paid_button():
    case = {"id": "c1", "language": "ru", "status": "qualified", "actions": [], "proposal": None,
            "payment": {"amount": 1990, "currency": "KZT", "status": "pending", "code": "KA-7F3K2Q",
                        "recipient_name": "Получатель", "kaspi_phone": "+7 700 000 00 00"}}
    screen = case_screen(case)
    assert "1 990 KZT" in screen.text and "KA-7F3K2Q" in screen.text and "+7 700 000 00 00" in screen.text
    assert ("Оплатить", "paid:c1") in screen.buttons[0]
    case["payment"]["status"] = "awaiting_confirmation"
    screen = case_screen(case)
    assert "Проверяем перевод" in screen.text and all(b[1] != "paid:c1" for row in screen.buttons for b in row)


LANGS = ("ru", "kk")


def _all_strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for v in node.values():
            yield from _all_strings(v)


def test_locales_have_no_emoji():
    import re

    from konsilier_bot.i18n import _load

    emoji = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\u23E9-\u23FA\uFE0F\u200D]")
    for lang in LANGS:
        bad = [s for s in _all_strings(_load(lang)) if emoji.search(s)]
        assert not bad, (lang, bad)


def test_start_and_help_name_the_real_scenario_count_and_support():
    from konsilier_bot.i18n import t

    scenarios = [p for p in (ROOT / "packs" / "kz" / "scenarios").glob("*.yaml") if not p.name.startswith("beta_")]
    for lang in LANGS:
        start, help_ = t("start", lang), t("help", lang)
        assert f"{len(scenarios)} " in start and f"{len(scenarios)} " in help_
        assert "konsilier.com/support" in start and "/help" in start
        assert "konsilier.com/support" in help_ and "info@konsilier.com" in help_
        assert "/new" in help_ and "/status" in help_


def test_errors_are_human_and_localized_without_codes():
    from konsilier_bot.api import ApiError
    from konsilier_bot.i18n import t
    from konsilier_bot.main import ERROR_CODES, error_text

    for lang in LANGS:
        for code in ERROR_CODES:
            text = error_text(ApiError(409, {"code": code, "message": code}), lang)
            assert text != f"errors.{code}" and code not in text and "(" not in text
        assert error_text(ApiError(429, {"code": "rate_limited"}), lang) == t("errors.too_many", lang)
        assert error_text(ApiError(502, "Bad Gateway"), lang) == t("errors.unavailable", lang)
        assert error_text(httpx.ConnectError("down"), lang) == t("errors.unavailable", lang)
        assert error_text(RuntimeError("boom"), lang) == t("error", lang)
    assert error_text(ApiError(429, {"code": "too_many_messages"}), "kk") != \
        error_text(ApiError(429, {"code": "too_many_messages"}), "ru")


def test_help_is_a_menu_command():
    from konsilier_bot.main import BOT_COMMANDS

    assert "help" in BOT_COMMANDS
