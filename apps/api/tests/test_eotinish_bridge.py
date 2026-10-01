"""Manual eOtinish bridge (owner's decision 01.10.2026): the person files on eotinish.kz themselves, then enters the
appeal number and date — we keep the proof (``Filing``) and run the response deadline from the entered date."""

from __future__ import annotations

import hashlib
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from konsilier.core.models import Action, Deadline, Filing
from konsilier.core.packs import load_pack

from .test_e2e import web_user
from .test_kz_end_to_end import _interview, _only
from .test_pilot_drafts import PACKS

KZ = load_pack(PACKS / "kz", PACKS)
SID = "kz.consumer.refund"


def test_pack_mapping_covers_every_eotinish_addressee():
    guide = KZ.appeal_portal
    assert guide is not None and guide.portal == "https://eotinish.kz"
    # every forum / authority whose channel is eotinish.kz has a «what to choose» entry
    for f in KZ.coverage.forums.values():
        if any(c.kind == "portal" and "eotinish.kz" in (c.url or "") for c in f.submission):
            assert f"forum:{f.id}" in guide.recipients, f.id
    for key, auth in KZ.manifest.authorities.items():
        if auth.submit_url and "eotinish.kz" in auth.submit_url:
            assert f"authority:{key}" in guide.recipients, key
    for key, rec in guide.recipients.items():
        assert {"ru", "kk", "en"} <= set(rec.recipient) and {"ru", "kk", "en"} <= set(rec.category), key


def _to_authority_step(ctx):
    """consumer_refund: the claim to the seller is refused → the complaint to the consumer-protection body."""
    _only(ctx, SID)
    api = web_user(ctx)
    cid = _interview(ctx, api, SID)
    first = api.post(f"/v1/cases/{cid}/actions/next")["case"]["actions"][-1]
    assert first["appeal_portal"] is None  # a claim to the seller does not go through eOtinish
    api.get(f"/v1/cases/{cid}/actions/{first['id']}/portal-filing", expect=409)
    api.post(f"/v1/cases/{cid}/actions/{first['id']}/submitted", json={})
    api.post(f"/v1/cases/{cid}/actions/{first['id']}/response", json={"response_class": "refusal"})
    case = api.post(f"/v1/cases/{cid}/actions/next")["case"]
    a = case["actions"][-1]
    assert a["action_id"] == "complaint_consumer_authority" and a["status"] == "ready", a
    return api, cid, a


def _backdate(ctx, action_id: str, days: int) -> None:
    with ctx.container.session_factory() as s:
        row = s.get(Action, uuid.UUID(action_id))
        row.created_at = row.created_at - timedelta(days=days)
        s.commit()


def test_guide_record_and_deadline_from_entered_date(ctx):
    api, cid, a = _to_authority_step(ctx)
    pack = ctx.container.packs.pack("KZ")
    # the step carries what to choose on the portal — from pack data
    assert a["appeal_portal"]["appeal_type"] == "complaint"
    assert a["appeal_portal"]["category"] == "Защита прав потребителей"
    assert a["appeal_portal"]["body_key"] == "authority:consumer_protection"
    assert a["filed"] is None
    guide = api.get(f"/v1/cases/{cid}/actions/{a['id']}/portal-filing").json()
    assert guide["portal"] == "https://eotinish.kz" and "ЖАЛОБА" in guide["text"].upper()
    assert guide["body"] == a["addressee"]["name"] and guide["filing"] is None

    # the receipt is uploaded with the existing evidence upload
    up = api.post(f"/v1/cases/{cid}/evidence", expect=201, data={"kind": "filing_receipt"},
                  files={"file": ("eotinish.png", b"\x89PNG\r\n\x1a\nfake", "image/png")})
    _backdate(ctx, a["id"], 10)
    filed_on = pack.local_now().date() - timedelta(days=3)
    out = api.post(f"/v1/cases/{cid}/actions/{a['id']}/portal-filing", expect=201, json={
        "number": "  ЖТ-2026-01234567 ", "filed_on": filed_on.isoformat(),
        "receipt_evidence_id": up["evidence"]["id"]})
    f = out["filing"]
    assert f["number"] == "ЖТ-2026-01234567" and f["filed_at"] == filed_on.isoformat()
    assert f["channel"] == "eotinish" and f["receipt_evidence_id"] == up["evidence"]["id"]
    assert f["category"] == "Защита прав потребителей" and f["appeal_type"] == "complaint"

    case = out["case"]
    assert case["status"] == "awaiting_response"
    step = case["actions"][-1]
    assert step["submitted_via"] == "eotinish" and step["filed"]["number"] == "ЖТ-2026-01234567"
    assert step["submitted_at"].startswith(filed_on.isoformat())
    # АППК, ст. 76 — 15 working days, counted from the date the person entered, not from today
    due = pack.add_days(filed_on, None, 15)
    assert step["deadline"]["due_date"] == due.isoformat()
    with ctx.container.session_factory() as s:
        dl = s.scalar(select(Deadline).where(Deadline.action_id == uuid.UUID(a["id"])))
        assert dl.due_date == due and dl.remind_before_days  # reminders run as for «Документ подан»
        row = s.scalar(select(Filing).where(Filing.action_id == uuid.UUID(a["id"])))
        act = s.get(Action, uuid.UUID(a["id"]))
        data = ctx.container.storage.get(act.pdf_key or act.docx_key)
        assert row.doc_sha256 == hashlib.sha256(data).hexdigest()
        assert row.body == a["addressee"]["name"] and row.body_key == "authority:consumer_protection"

    # one filing per document
    r = ctx.client.post(f"/v1/cases/{cid}/actions/{a['id']}/portal-filing", headers=api.h,
                        json={"number": "ЖТ-2026-7", "filed_on": filed_on.isoformat()})
    assert r.status_code == 409
    # the guide now shows the record
    assert api.get(f"/v1/cases/{cid}/actions/{a['id']}/portal-filing").json()["filing"]["number"] == "ЖТ-2026-01234567"


def test_validation_of_number_date_and_receipt(ctx):
    api, cid, a = _to_authority_step(ctx)
    today = ctx.container.packs.pack("KZ").local_now().date()
    url = f"/v1/cases/{cid}/actions/{a['id']}/portal-filing"

    def post(**body):
        return ctx.client.post(url, headers=api.h, json={"number": "ЖТ-2026-1", "filed_on": today.isoformat(), **body})

    for bad in ("", "  ", "ab", "без номера", "<script>1</script>", "1" * 70):
        r = post(number=bad)
        assert r.status_code == 422, (bad, r.text)
    r = post(filed_on=(today + timedelta(days=1)).isoformat())
    assert r.status_code == 422 and r.json()["detail"]["code"] == "date_in_future"
    r = post(filed_on=(today - timedelta(days=30)).isoformat())  # before the document was made
    assert r.status_code == 422 and r.json()["detail"]["code"] == "date_before_document"
    r = post(filed_on="31.02.2026")
    assert r.status_code == 422
    r = post(receipt_evidence_id=str(uuid.uuid4()))
    assert r.status_code == 422 and r.json()["detail"]["code"] == "bad_receipt"
    # nothing was recorded by the refused attempts
    assert api.get(f"/v1/cases/{cid}").json()["actions"][-1]["submitted_at"] is None
    # today is fine; the deadline starts today
    out = post(number="№ 12345").json()
    assert out["filing"]["number"] == "№ 12345"
    due = ctx.container.packs.pack("KZ").add_days(today, None, 15)
    assert out["case"]["actions"][-1]["deadline"]["due_date"] == due.isoformat()


def test_only_own_case(ctx):
    api, cid, a = _to_authority_step(ctx)
    other = web_user(ctx)
    today = ctx.container.packs.pack("KZ").local_now().date().isoformat()
    url = f"/v1/cases/{cid}/actions/{a['id']}/portal-filing"
    assert ctx.client.get(url, headers=other.h).status_code == 404
    assert ctx.client.post(url, headers=other.h, json={"number": "ЖТ-1", "filed_on": today}).status_code == 404
    # someone else's evidence can not become the receipt
    ocid = other.post("/v1/cases", expect=201, json={"text": "Купил телефон, сломался, деньги не возвращают 150000",
                                                       "country": "KZ"})["case"]["id"]
    ev = other.post(f"/v1/cases/{ocid}/evidence", expect=201, data={"kind": "other"},
                    files={"file": ("x.txt", "чужой файл".encode(), "text/plain")})["evidence"]["id"]
    r = ctx.client.post(url, headers=api.h, json={"number": "ЖТ-1", "filed_on": today, "receipt_evidence_id": ev})
    assert r.status_code == 422
    # a receipt added later — only to one's own filing
    api.post(url, expect=201, json={"number": "ЖТ-1", "filed_on": today})
    up = api.post(f"/v1/cases/{cid}/evidence", expect=201, data={"kind": "filing_receipt"},
                  files={"file": ("r.pdf", b"%PDF-1.4 receipt", "application/pdf")})["evidence"]["id"]
    assert ctx.client.post(url + "/receipt", headers=other.h, json={"evidence_id": up}).status_code == 404
    out = api.post(url + "/receipt", json={"evidence_id": up})
    assert out["filing"]["receipt_evidence_id"] == up


# ---------------------------------------------------------------- «3 клика»: the number and date are read, not typed
# A typical eOtinish confirmation. The portal does not publish its number format; its interface prints
# «№{{appealNumber}}, поданного {{appealCreatedDate}}» (eotinish.kz/ru/faq, texts checked 01.10.2026).
def _confirmation(d) -> str:
    return (f"eOtinish: Ваше обращение принято. Обращение № ЖТ-2026-00012345 от {d.strftime('%d.%m.%Y')}. "
            "Срок рассмотрения — 15 рабочих дней. Тел. для справок +7 701 123 45 67.")


def test_number_and_date_found_in_confirmation_texts():
    from datetime import date

    from konsilier.core.appeal_portal import find_number_and_date

    g, today = KZ.appeal_portal, date(2026, 10, 1)
    cases = {
        "Обращение № ЖТ-2026-00012345 от 01.10.2026": ("ЖТ-2026-00012345", date(2026, 10, 1)),
        "Номер обращения: ЖТ-2026-00012345. Дата регистрации 30.09.2026": ("ЖТ-2026-00012345", date(2026, 9, 30)),
        "Жалоба подается в связи с истечением срока обращения №ЗТ-Ж-2026-77, поданного 2026-09-01":
            ("ЗТ-Ж-2026-77", date(2026, 9, 1)),
        "Өтініш нөмірі ЖТ-2026-1, 01.10.2026": ("ЖТ-2026-1", date(2026, 10, 1)),
        "номер телефона +77011234567": (None, None),
        "№ ЖТ-2026-5 от 05.10.2026": ("ЖТ-2026-5", None),  # a future date is never taken
    }
    for text, want in cases.items():
        assert find_number_and_date(g, text, today) == want, text


def test_proof_text_is_read_and_confirmed_in_one_tap(ctx):
    api, cid, a = _to_authority_step(ctx)
    pack = ctx.container.packs.pack("KZ")
    _backdate(ctx, a["id"], 10)
    filed_on = pack.local_now().date() - timedelta(days=2)
    url = f"/v1/cases/{cid}/actions/{a['id']}/portal-filing"
    # the notification e-mail / SMS forwarded as a text file
    got = api.post(url + "/proof", expect=201,
                   files={"file": ("eotinish.txt", _confirmation(filed_on).encode(), "text/plain")})
    assert got == {"evidence_id": got["evidence_id"], "number": "ЖТ-2026-00012345",
                   "filed_on": filed_on.isoformat(), "found": True, "read_by": "text"}
    # nothing is filed until the person confirms
    assert api.get(f"/v1/cases/{cid}").json()["actions"][-1]["submitted_at"] is None
    out = api.post(url, expect=201, json={"number": got["number"], "filed_on": got["filed_on"],
                                          "receipt_evidence_id": got["evidence_id"]})
    assert out["filing"]["source"] == "receipt_read" and out["filing"]["receipt_evidence_id"] == got["evidence_id"]
    step = out["case"]["actions"][-1]
    assert step["submitted_at"].startswith(filed_on.isoformat())
    assert step["deadline"]["due_date"] == pack.add_days(filed_on, None, 15).isoformat()


def test_proof_pasted_text_and_corrected_value(ctx):
    api, cid, a = _to_authority_step(ctx)
    today = ctx.container.packs.pack("KZ").local_now().date()
    url = f"/v1/cases/{cid}/actions/{a['id']}/portal-filing"
    got = api.post(url + "/proof", expect=201, data={"text": _confirmation(today)})
    assert got["found"] and got["number"] == "ЖТ-2026-00012345"
    # corrected by hand → recorded as entered by the person
    out = api.post(url, expect=201, json={"number": "ЖТ-2026-00012346", "filed_on": today.isoformat(),
                                          "receipt_evidence_id": got["evidence_id"]})
    assert out["filing"]["source"] == "client_entered"
    # empty request
    assert ctx.client.post(url + "/proof", headers=api.h, data={"text": "  "}).status_code == 422


def test_proof_screenshot_read_by_model_or_falls_back_to_manual(ctx):
    api, cid, a = _to_authority_step(ctx)
    today = ctx.container.packs.pack("KZ").local_now().date()
    url = f"/v1/cases/{cid}/actions/{a['id']}/portal-filing"
    png = ("screen.png", b"\x89PNG\r\n\x1a\nscreenshot", "image/png")

    # image reading off (or the model sees nothing): no number → the manual fields are the fallback
    got = api.post(url + "/proof", expect=201, files={"file": png})
    assert got["found"] is False and got["number"] is None and got["read_by"] is None and got["evidence_id"]

    # a fake extractor standing in for the model that reads screenshots (EXTRACT_IMAGES_WITH_LLM on)
    ctx.container.engine.config.extract_images_with_llm = True
    seen = []

    def fake(p):
        seen.append(p)
        return {"number": "ЖТ-2026-00012345", "date": today.isoformat()}
    ctx.llm._extract_filing_proof = fake
    got = api.post(url + "/proof", expect=201, files={"file": png})
    assert seen and got["found"] and got["read_by"] == "model"
    assert got["number"] == "ЖТ-2026-00012345" and got["filed_on"] == today.isoformat()
    # the model's future date is not trusted
    ctx.llm._extract_filing_proof = lambda p: {"number": "ЖТ-1", "date": (today + timedelta(days=3)).isoformat()}
    got = api.post(url + "/proof", expect=201, files={"file": png})
    assert got["number"] == "ЖТ-1" and got["filed_on"] is None and got["found"] is False
    # someone else can not upload proofs into this case
    other = web_user(ctx)
    r = ctx.client.post(url + "/proof", headers=other.h, data={"text": _confirmation(today)})
    assert r.status_code == 404


def test_one_filings_table_for_the_portal_and_the_send_wizard(ctx):
    """One «Подача» table (integrations-plan 7.3): the send wizard's plan shows the portal step for a state body;
    the registered appeal is one per step, while letters / messenger sendings of the same document are not limited
    by it."""
    api, cid, a = _to_authority_step(ctx)
    plan = api.get(f"/v1/cases/{cid}/actions/{a['id']}/send").json()
    assert [s["channel"] for s in plan["route"]] == ["portal"]
    step = plan["route"][0]
    assert step["portal"] == "eOtinish" and step["href"] == "https://eotinish.kz" and not step.get("done")

    filed_on = ctx.container.packs.pack("KZ").local_now().date()
    api.post(f"/v1/cases/{cid}/actions/{a['id']}/portal-filing", expect=201,
             json={"number": "ЖТ-2026-555", "filed_on": filed_on.isoformat()})
    plan = api.get(f"/v1/cases/{cid}/actions/{a['id']}/send").json()
    assert plan["route"][0]["done"] is True and plan["filings"] == []  # the appeal is shown as `filed`, not a letter
    view = api.get(f"/v1/cases/{cid}").json()["actions"][-1]
    assert view["filed"]["number"] == "ЖТ-2026-555" and view["filings"] == []

    aid = uuid.UUID(a["id"])
    with ctx.container.session_factory() as s:
        row = s.scalar(select(Filing).where(Filing.action_id == aid))
        assert row.status == "filed" and row.appeal_number == "ЖТ-2026-555" and row.external_id is None
        common = {"case_id": row.case_id, "action_id": aid, "user_id": row.user_id}
        # several sendings of the same document by other channels are fine
        s.add_all([Filing(**common, channel="email", recipient="dep@example.kz", status="sent"),
                   Filing(**common, channel="whatsapp", recipient="+77010000000", status="sent")])
        s.commit()
        # a second registered appeal for the same step is refused by the database
        s.add(Filing(**common, channel=row.channel, recipient="x", status="filed", appeal_number="2"))
        with pytest.raises(IntegrityError):
            s.commit()
        s.rollback()
    view = api.get(f"/v1/cases/{cid}").json()["actions"][-1]
    assert [f["channel"] for f in view["filings"]] == ["email", "whatsapp"]
    assert view["filed"]["number"] == "ЖТ-2026-555"
