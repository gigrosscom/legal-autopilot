"""Beta scenarios (EXPERIMENTAL_SCENARIOS): help with a document package (tender bid, admission, visa, ИП) and
business disputes. Each one goes from the story to ready documents; the classifier picks it from typical phrases
(mock LLM and keyword fallback); with the flag off none of them is offered."""

from __future__ import annotations

import os
import re
import uuid
from pathlib import Path

import pytest

from konsilier.core import ai
from konsilier.core.documents import LibreOfficeConverter, docx_text
from konsilier.core.llm import LLMError, RedactingLLM
from konsilier.core.models import Action
from konsilier.core.packs import load_pack
from konsilier.core.pii import PiiVault

from .test_e2e import web_user
from .test_pilot_drafts import DRAFT_WORDS, NEUTRAL_NOTE_RU, PACKS

KZ = load_pack(PACKS / "kz", PACKS)
BETA = sorted(s.id for s in KZ.scenarios.values() if s.beta)
SERVICES = [sid for sid in BETA if KZ.scenarios[sid].kind == "service"]

# answers by field name; anything else is answered by type (see _answer)
ANSWERS = {
    "applicant_iin": "900101300128", "applicant_bin": "900101300128", "respondent_bin": "123456789012",
    "applicant_name": "Иванов Иван Иванович", "representative": "Директор Иванов И. И.",
    "applicant_address": "Алматы, ул. Абая 1", "applicant_phone": "+7 701 123 45 67",
    "applicant_email": "test@example.com", "passport_number": "N12345678",
}
_UNFILLED = re.compile(r"\{[a-z_]+\}")


def _answer(q: dict, skip_optional: bool) -> str:
    if q["type"] == "evidence" or (skip_optional and q["optional"]):
        return "пропустить"
    if q["field"] in ANSWERS:
        return ANSWERS[q["field"]]
    return {"date": "01.09.2026", "money": "1500000", "number": "3", "email": "test@example.com",
            "phone": "+7 701 123 45 67", "longtext": "Подробное описание ситуации заявителя."}.get(
        q["type"], f"Ответ {q['field']}")


def only(ctx, sid: str) -> None:
    """Offer only the scenario under test (the others stay loaded for cases already open)."""
    for pack in ctx.container.packs.packs.values():
        for other, sc in list(pack.scenarios.items()):
            pack.scenarios[other] = sc.model_copy(update={"published": other == sid, "beta": sc.beta and other == sid})


def run_to_documents(ctx, sid: str, skip_optional: bool = False) -> tuple[dict, dict, str]:
    only(ctx, sid)
    sc = KZ.scenarios[sid]
    api = web_user(ctx)
    case = api.post("/v1/cases", expect=201, json={"text": sc.classification.examples["ru"][0], "country": "KZ"})["case"]
    assert case["scenario"]["id"] == sid
    assert case["scenario"]["beta"] is True and case["scenario"]["disclaimer"]
    q = case["question"]
    guard = 0
    while q is not None:
        out = api.answer(case["id"], _answer(q, skip_optional))
        assert out["reply"]["error"] is None, (q["field"], out["reply"])
        q = out["case"]["question"]
        guard += 1
        assert guard < 40
    view = api.get(f"/v1/cases/{case['id']}").json()
    body = api.post(f"/v1/cases/{case['id']}/actions/next")["case"]
    action = body["actions"][0]
    assert action["status"] == "ready", action  # self-service: no lawyer approval for a package
    assert action["instructions"] and not any(_UNFILLED.search(s) for s in action["instructions"])
    with ctx.container.session_factory() as s:
        docx = ctx.container.storage.get(s.get(Action, uuid.UUID(action["id"])).docx_key)
    text = docx_text(docx)
    if os.environ.get("BETA_DUMP_DIR"):  # manual review of the generated packages
        Path(os.environ["BETA_DUMP_DIR"], f"{sid}{'-short' if skip_optional else ''}.docx").write_bytes(docx)
    return view, action, text


@pytest.mark.parametrize("sid", BETA)
def test_beta_scenario_story_to_documents(ctx, sid):
    view, action, text = run_to_documents(ctx, sid)
    sc = KZ.scenarios[sid]
    assert not _UNFILLED.search(text), _UNFILLED.findall(text)
    assert "{{" not in text and "{%" not in text
    assert NEUTRAL_NOTE_RU in text and not DRAFT_WORDS.search(text)
    assert sc.disclaimer["ru"] in text or sc.kind == "dispute"
    for src in sc.sources:
        assert src.url in text or sc.kind == "dispute"
    if sc.kind == "service":
        for sec in sc.actions[0].package:
            if not sec.if_:
                assert sec.title["ru"] in text, sec.id
        assert view["plan"]["attachments"], "personal checklist is shown before the document is prepared"
        assert "☐" in text
        assert "гарант" in sc.disclaimer["ru"] and "гарант" in sc.disclaimer["kk"].replace("кепілдік", "гарант")  # no promise of the result
    for ref in sc.actions[0].norm_refs:
        if sc.kind == "dispute" and "TODO" not in ref:
            assert ref in text


@pytest.mark.parametrize("sid", SERVICES)
def test_service_checklist_is_personal(ctx, sid):
    """Optional answers switch checklist lines on; skipped ones leave them out."""
    sc = KZ.scenarios[sid]
    conditional = [ln for sec in sc.actions[0].package for ln in (*sec.text, *sec.check) if ln.if_]
    if not conditional:
        pytest.skip("no optional lines")
    _, _, full = run_to_documents(ctx, sid)
    _, _, short = run_to_documents(ctx, sid, skip_optional=True)
    assert len(short) < len(full)
    assert not _UNFILLED.search(short)


def test_visa_package_as_pdf(ctx):
    conv = LibreOfficeConverter("soffice")
    if not conv.available():
        pytest.skip("LibreOffice is not installed")
    ctx.container.engine.pdf = conv
    _, action, _ = run_to_documents(ctx, "kz.services.visa_schengen_de")
    assert action["has_pdf"]
    with ctx.container.session_factory() as s:
        pdf = ctx.container.storage.get(s.get(Action, uuid.UUID(action["id"])).pdf_key)
    assert pdf[:4] == b"%PDF"


# ---------------------------------------------------------------- classification
PHRASES = {
    "kz.services.tender_application": ["Помогите подготовить заявку на тендер на goszakup", "участвуем в госзакупках, нужна конкурсная документация и опись"],
    "kz.services.university_admission": ["Хочу поступить в вуз, сдал ЕНТ, нужны документы в приемную комиссию", "как поступить в университет на грант, какие документы для поступления"],
    "kz.services.study_abroad": ["Хочу поступить за границу, нужен мотивационное письмо и CV", "учёба за рубежом: помогите с резюме и motivation letter"],
    "kz.services.visa_schengen_de": ["Нужна шенгенская виза в Германию, какие документы", "еду в германию туристом, виза"],
    "kz.services.visa_us": ["Хочу получить визу в США, заполнить DS-160", "американская виза B1/B2 на собеседование"],
    "kz.services.visa_uk": ["Нужна виза в Великобританию, standard visitor", "еду в Лондон, британская виза"],
    "kz.services.ip_registration": ["Хочу открыть ИП, как зарегистрировать ИП", "регистрация ИП онлайн"],
    "kz.services.ip_closure": ["Хочу закрыть ИП, прекращение деятельности ИП", "как ликвидировать ИП"],
    "kz.business.debt_claim": ["Контрагент не оплатил счёт по договору поставки, ТОО должно нам деньги", "дебиторская задолженность, претензия контрагенту о долге"],
    "kz.business.supply_claim": ["Поставщик недопоставил товар по договору поставки", "поставщик привёз некачественный товар, претензия поставщику"],
    "kz.business.lease_termination": ["Хотим расторгнуть договор аренды офиса и вернуть обеспечительный платёж", "арендодатель не возвращает гарантийный взнос за помещение"],
    "kz.business.tax_audit_appeal": ["Пришло уведомление о результатах налоговой проверки, хотим обжаловать", "доначислили налоги по итогам проверки КГД"],
    "kz.business.inspection_complaint": ["Проверка акимата нарушила наши права, жалоба на действия проверяющих", "незаконная проверка контролирующего органа"],
    "kz.business.procurement_complaint": ["Хотим обжаловать итоги госзакупок, заказчик неправильно отклонил заявку", "жалоба на протокол итогов конкурса госзакупок"],
}


def test_every_beta_scenario_has_phrases():
    assert set(PHRASES) == set(BETA)


@pytest.mark.parametrize("sid", BETA)
def test_classifier_picks_beta_scenario_with_mock(ctx, sid):
    """All published scenarios (old and beta) compete; the mock model is keyword-driven like the fallback."""
    pack = ctx.container.packs
    candidates = pack.published("KZ")
    llm = RedactingLLM(ctx.llm, PiiVault({}))
    for phrase in PHRASES[sid]:
        got, conf, _ = ai.qualify(llm, candidates, pack.packs, phrase, "ru")
        assert got == sid, (phrase, got)
        assert conf > 0


class _Down:
    def complete_json(self, **kw):
        raise LLMError("down")


@pytest.mark.parametrize("sid", BETA)
def test_classifier_keyword_fallback(ctx, sid):
    pack = ctx.container.packs
    llm = RedactingLLM(_Down(), PiiVault({}))
    for phrase in PHRASES[sid]:
        got, conf, why = ai.qualify(llm, pack.published("KZ"), pack.packs, phrase, "ru")
        assert got == sid, (phrase, got, why)
        assert conf <= 0.55  # keyword matches are capped → reviewed


def test_old_scenarios_still_win_their_stories(ctx):
    """Beta keywords must not steal classic disputes."""
    pack = ctx.container.packs
    llm = RedactingLLM(ctx.llm, PiiVault({}))
    for sc in KZ.scenarios.values():
        if not sc.published:
            continue
        for phrase in sc.classification.examples.get("ru", ()):
            got, _, _ = ai.qualify(llm, pack.published("KZ"), pack.packs, phrase, "ru")
            assert not (got and KZ.scenarios[got].beta), (sc.id, phrase, got)


# ---------------------------------------------------------------- flag
def test_flag_off_hides_beta(ctx):
    ctx.container.packs.experimental = False
    listed = {s["id"] for p in ctx.client.get("/v1/packs").json() for s in p["scenarios"]}
    assert listed and not listed & set(BETA)
    assert not {s.id for s in ctx.container.packs.published("KZ")} & set(BETA)
    api = web_user(ctx)
    for sid in BETA:
        case = api.post("/v1/cases", expect=201, json={"text": PHRASES[sid][0], "country": "KZ"})["case"]
        assert (case["scenario"] or {}).get("id") not in BETA


def test_flag_on_lists_beta_with_mark(ctx):
    ctx.container.packs.experimental = True
    scen = {s["id"]: s for p in ctx.client.get("/v1/packs").json() for s in p["scenarios"]}
    for sid in BETA:
        assert scen[sid]["beta"] is True


def test_flag_defaults_off_in_settings(monkeypatch):
    from konsilier.config import Settings

    monkeypatch.delenv("EXPERIMENTAL_SCENARIOS", raising=False)
    assert Settings(_env_file=None).experimental_scenarios is False
