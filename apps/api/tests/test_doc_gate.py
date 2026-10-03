"""PM 02.10 (owner: «грубые ошибки в документах»): every document is checked before it is given — core/docgate.py.
1) [brackets], «уточнит юрист», «рассчитает юрист», «Проверьте данные»; 2) the applicant's name as the other side's;
3) empty requisites; 4) one norm twice in a row. The client is asked one field; what only a lawyer can fix goes to
the lawyer's check, never to the client."""

from __future__ import annotations

import uuid

from konsilier.core import docgate
from konsilier.core.documents import docx_text
from konsilier.core.models import Action, Case

from .test_e2e import web_user
from .test_payment import qualified_case

PARTIES = {"applicant": {"name": "Тестов Тест Тестович"}, "respondent": {"name": "ТОО «Техномир»"}}
FIELDS = {"applicant": {"name": "applicant_name"}, "respondent": {"name": "seller_name"}}
WORDS = ("уточнит юрист", "рассчитает юрист", "Проверьте данные", "Проверьте сведения")


def _check(text="Претензия.", parties=PARTIES, addressee=None, required=None):
    return docgate.check(text, words=WORDS, norm_words=("стать", "закон", "кодекс"),
                         addressee=addressee or {"name": "ТОО «Техномир»"}, parties=parties, fields=FIELDS,
                         required=required or {})


def test_markers_and_brackets():
    assert _check() == []
    for text in ("Цена иска: [рассчитает юрист].", "Адрес: [Адрес продавца]", "Размер — уточнит юрист.",
                 "Подготовлено с помощью ИИ. Проверьте данные перед подачей.", "Проверьте сведения."):
        found = _check(text)
        assert found and found[0].kind == "marker" and not found[0].client_can_fix, text


def test_the_applicants_name_as_the_other_side_asks_that_field():
    swapped = {**PARTIES, "respondent": {"name": "  тестов тест тестович "}}
    found = _check(parties=swapped)
    assert found[0].kind == "swapped_party" and found[0].field == "seller_name"


def test_empty_requisites():
    found = _check(parties={**PARTIES, "respondent": {"name": ""}}, addressee={"name": ""},
                   required={"amount": None, "purchase_date": "12.08.2026"})
    kinds = {(p.kind, p.detail) for p in found}
    assert ("empty", "addressee") in kinds and ("empty", "respondent.name") in kinds and ("empty", "amount") in kinds
    assert found[0].client_can_fix  # the client is asked first


def test_one_norm_twice_in_a_row():
    text = "Согласно статье 15 Закона о защите прав потребителей. Согласно статье 15 Закона о защите прав потребителей."
    assert [p.kind for p in _check(text)] == ["repeated"]
    assert _check("Прошу вернуть деньги. Прошу вернуть деньги.") == []  # not a norm: not this check


def _doc_text(ctx, action_id):
    with ctx.container.session_factory() as s:
        return docx_text(ctx.container.storage.get(s.get(Action, uuid.UUID(action_id)).docx_key))


def test_a_swapped_seller_is_asked_before_the_document_is_made(ctx):
    api, cid = qualified_case(ctx)
    with ctx.container.session_factory() as s:  # as the documents of 02.10: the seller's name is the applicant's
        c = s.get(Case, uuid.UUID(cid))
        c.facts = {**c.facts, "seller_name": c.facts["applicant_name"]}
        s.commit()
    r = api.c.post(f"/v1/cases/{cid}/actions/next", headers=api.h)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "applicant_data_required"
    assert [f["field"] for f in r.json()["detail"]["fields"]] == ["seller_name"]
    with ctx.container.session_factory() as s:
        assert not s.get(Case, uuid.UUID(cid)).actions  # nothing given
    api.post(f"/v1/cases/{cid}/facts", json={"values": {"seller_name": "ТОО «Техномир»"}})
    out = api.post(f"/v1/cases/{cid}/actions/next")
    assert out["action_id"] and "ТОО «Техномир»" in _doc_text(ctx, out["action_id"])


def test_the_applicants_name_is_never_taken_as_the_sellers(ctx):
    api, cid = qualified_case(ctx)
    with ctx.container.session_factory() as s:
        me = s.get(Case, uuid.UUID(cid)).facts["applicant_name"]
    r = api.c.post(f"/v1/cases/{cid}/facts", headers=api.h, json={"values": {"seller_name": me}})
    assert r.status_code == 422 and r.json()["detail"]["fields"] == {"seller_name": "own"}


def test_a_claim_without_a_checked_norm_prints_no_lawyer_marker(ctx):
    from .test_coverage_levels import WAGES
    from .conftest import hide_scenarios

    hide_scenarios(ctx, "kz.labor.")
    api = web_user(ctx)
    case = api.post("/v1/cases", expect=201, json={"text": WAGES, "country": "KZ"})["case"]
    from .test_coverage_levels import _fill_and_prepare
    action = _fill_and_prepare(api, case["id"], case)
    assert action["approval_status"] == "not_required" and action["downloadable"]
    text = _doc_text(ctx, action["id"])
    assert "уточнит юрист" not in text and "[" not in text and "Правовое основание:\n" not in text + "\n"


def test_what_only_a_lawyer_can_fix_goes_to_the_lawyer(ctx, monkeypatch):
    api, cid = qualified_case(ctx)
    engine = ctx.container.engine
    monkeypatch.setattr(engine, "check_document",
                        lambda *a, **k: [docgate.Problem("marker", "[рассчитает юрист]")])
    out = api.post(f"/v1/cases/{cid}/actions/next")
    action = out["case"]["actions"][-1]
    assert action["approval_status"] == "pending" and action["downloadable"] is False


def test_old_documents_lose_the_forbidden_phrase(ctx):
    """Owner 02.10: «Проверьте данные перед подачей» out of the documents already given; the rest stays."""
    import io

    from docx import Document

    from konsilier.core.reissue import reissue_all, strip_old_phrases

    api, cid = qualified_case(ctx)
    action_id = api.post(f"/v1/cases/{cid}/actions/next")["action_id"]
    with ctx.container.session_factory() as s:
        a = s.get(Action, uuid.UUID(action_id))
        doc = Document(io.BytesIO(ctx.container.storage.get(a.docx_key)))
        doc.sections[0].footer.add_paragraph("Подготовлено с помощью ИИ (Konsilier AI). Проверьте данные перед подачей.")
        buf = io.BytesIO()
        doc.save(buf)
        ctx.container.storage.put(a.docx_key, buf.getvalue())
        before = docx_text(buf.getvalue())
        assert reissue_all(s, ctx.container.storage, None, apply=False)["with_phrase"] == 1  # dry run: counted only
        assert "Проверьте данные" in docx_text(ctx.container.storage.get(a.docx_key))
        out = reissue_all(s, ctx.container.storage, None, apply=True)
        s.commit()
        after = docx_text(ctx.container.storage.get(a.docx_key))
    assert out["with_phrase"] == 1 and "Проверьте" not in after
    assert "Подготовлено с помощью ИИ (Konsilier AI)." in after
    assert after.replace(" ", "") == before.replace("Проверьте данные перед подачей.", "").replace(" ", "")
    assert strip_old_phrases(ctx.container.storage.get(a.docx_key)) is None  # nothing left to clean


def test_amounts_are_printed_with_the_sign_never_the_code(ctx):
    """QA BUG-22: «380 000 KZT» in the demands → «380 000 ₸ (… тенге)»; «KZT» is a marker of the check too."""
    api, cid = qualified_case(ctx)
    text = _doc_text(ctx, api.post(f"/v1/cases/{cid}/actions/next")["action_id"])
    assert "KZT" not in text and "₸" in text
    assert [p.kind for p in docgate.markers("Сумма 380 000 KZT.", ("KZT",))] == ["marker"]


def test_the_document_has_no_service_line_and_no_uncounted_penalty(ctx):
    from .conftest import hide_scenarios
    from .test_coverage_levels import WAGES, _fill_and_prepare

    hide_scenarios(ctx, "kz.labor.")
    api = web_user(ctx)
    case = api.post("/v1/cases", expect=201, json={"text": WAGES, "country": "KZ"})["case"]
    text = _doc_text(ctx, _fill_and_prepare(api, case["id"], case)["id"])
    assert "Дата события:" not in text and "пен" not in text.lower().replace("пенсион", "")


def test_the_draft_shows_the_sign_not_the_code(ctx):
    """QA BUG-22: the draft on the case page read «… KZT»; it is made with the same last pass as the document."""
    from .test_draft_prefill import to_draft

    api, case = to_draft(ctx)
    cid = case["id"]
    with ctx.container.session_factory() as s:
        c = s.get(Case, uuid.UUID(cid))
        c.facts = {**c.facts, "amount": "150000"}
        s.commit()
    d = api.get(f"/v1/cases/{cid}/draft").json()
    text = d.get("visible", "") + d.get("hidden", "") + d.get("text", "")
    assert "KZT" not in text


def test_a_value_nobody_told_is_asked_not_printed():
    """PM 02.10 (R-29): a sum, a date or the other side's name that is neither typed by the person nor found in their
    story, chat or files is a made-up value — the person is asked that field."""
    said = "Купил телевизор в Техномире 12.08.2026 за 250 000 тенге"
    ok = {"amount": ("money", "250000"), "purchase_date": ("date", "12.08.2026"), "seller_name": ("name", "ТОО «Техномир»")}
    assert docgate.invented(ok, said, set()) == []
    made_up = {"amount": ("money", "99000"), "purchase_date": ("date", "01.09.2026"), "seller_name": ("name", "ТОО «Ромашка»")}
    found = docgate.invented(made_up, said, set())
    assert {p.field for p in found} == {"amount", "purchase_date", "seller_name"} and all(p.client_can_fix for p in found)
    assert docgate.invented(made_up, said, {"amount", "purchase_date", "seller_name"}) == []  # typed: the person's word
    assert [p.kind for p in docgate.markers("Требования по сути обращения.", ("по сути обращения",))] == ["marker"]


def test_a_made_up_sum_stops_the_document(ctx):
    api, cid = qualified_case(ctx)
    with ctx.container.session_factory() as s:  # a sum the model wrote in, not told anywhere
        c = s.get(Case, uuid.UUID(cid))
        c.facts = {**c.facts, "amount": "987654"}
        s.commit()
    from sqlalchemy import select
    from konsilier.core.models import AuditLog
    with ctx.container.session_factory() as s:  # and never typed by the person
        for row in s.scalars(select(AuditLog).where(AuditLog.case_id == uuid.UUID(cid), AuditLog.event == "answered")):
            if (row.data or {}).get("field") == "amount":
                s.delete(row)
        s.commit()
    r = api.c.post(f"/v1/cases/{cid}/actions/next", headers=api.h)
    assert r.status_code == 422 and [f["field"] for f in r.json()["detail"]["fields"]] == ["amount"]
