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
    assert s.text == "БИН?" and s.buttons == [[("⏭ Пропустить", "skip:c1")]]


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
                        soffice_bin="")
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
        for answer in ("МФО Ромашка", "пропустить", "пропустить", "пропустить", "Иванов Иван",
                       "900101300123", "+77010000000", "пропустить", "пропустить"):
            out = await api.message("42", cid, answer)
        assert out["case"]["status"] == "qualified"
        out = await api.prepare_next("42", cid)
        action = out["case"]["actions"][0]
        doc = await api.document("42", cid, action["id"], "docx")
        assert doc[:2] == b"PK"
        out = await api.submitted("42", cid, action["id"])
        out = await api.response("42", cid, action["id"], no_response=True)
        assert out["proposal"]["action_id"] == "complaint_arrf"
        screen = case_screen(out["case"])
        assert ("📄 Подготовить документ", f"prep:{cid}") in screen.buttons[0]
        await api.close()

    asyncio.run(scenario())
