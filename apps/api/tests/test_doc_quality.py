"""Owner 01.10, the first paid claim (kz.consumer.refund): what was wrong in its text, fixed for every scenario.
1 the client's own e-mail as the seller's · 2 a description as the seller's address · 3 names and addresses in
lower case · 4 the purchase told twice · 5 «приобрел(а)» · 6 a service called «бракованный товар» · 7 the same file
listed twice · 8 two AI notes · 9 «10 352 KZT»."""
from __future__ import annotations

import uuid

from konsilier.core import ai
from konsilier.core.documents import docx_text
from sqlalchemy import func, select

from konsilier.core.models import Action, Case, Invoice, User
from konsilier.core.polish import (amounts_in_words, gender_forms, gender_from_id, gender_from_name, number_words,
                                   tidy_address, tidy_name)

from .test_e2e import web_user

STORY = "Купил токены в интернет-сервисе ИИ антропик за 10352 тенге 17.09.2026, сервис не работает, деньги не возвращают"
FACTS = {"seller_name": "антропик", "goods_description": "токены для ИИ-сервиса", "applicant_name": "Ахметов Ерлан Серикович",
         "applicant_phone": "+7 701 555 12 12", "seller_email": "client.self@mail.kz",
         "seller_address": "интернет сервис ии антропик", "applicant_address": "алматы сейдимбек 222",
         "purchase_date": "2026-09-17", "amount": "10352.00", "problem_description": "Сервис не работает, деньги не вернули."}


def claim_text(ctx, facts: dict | None = None, narrative: str | None = None, email: str = "client.self@mail.kz") -> tuple[str, dict]:
    ctx.settings.payment_requires_contact = False
    ctx.container.engine.config.intake_max_questions = -1
    api = web_user(ctx)
    cid = api.post("/v1/cases", expect=201, json={"text": STORY, "country": "KZ"})["case"]["id"]
    for _ in range(2):  # the same statement uploaded twice
        api.post(f"/v1/cases/{cid}/evidence", expect=201, data={"kind": "receipt"},
                 files={"file": ("gold_statement.pdf", b"%PDF-1.4 same", "application/pdf")})
    with ctx.container.session_factory() as s:
        c = s.get(Case, uuid.UUID(cid))
        vals = {**FACTS, **(facts or {})}
        c.facts = {**(c.facts or {}), **vals}
        c.skipped_fields = [f for f in (c.skipped_fields or []) if f.split(":")[-1] not in vals]
        if narrative is not None:
            c.narrative = narrative
        s.get(User, c.owner_id).email = email  # the client's own address
        s.commit()
    api.post(f"/v1/cases/{cid}/payment", json={"purpose": "document"})
    out = api.post(f"/v1/cases/{cid}/actions/next")
    with ctx.container.session_factory() as s:
        a = s.get(Action, uuid.UUID(out["action_id"]))
        return docx_text(ctx.container.storage.get(a.docx_key)), dict(a.addressee)


def test_claim_text_is_clean(ctx):
    text, addressee = claim_text(ctx)
    assert "client.self@mail.kz" not in text and addressee["email"] is None  # 1
    assert "интернет сервис" not in text and addressee["address"] == ""  # 2
    assert "Кому: Антропик" in text and "Адрес: Алматы, ул. Сейдимбек, 222" in text  # 3
    assert "(а)" not in text and "мною была совершена покупка" in text  # 5 (the template line is neutral)
    assert text.count("gold_statement.pdf") == 1  # 7
    assert text.count("Подготовлено с помощью ИИ (Konsiliér AI). Проверьте данные перед подачей.") == 1  # 8
    assert "IT-сервисом" not in text
    assert "KZT" not in text  # 9
    assert "10\u00a0352 ₸ (десять тысяч триста пятьдесят два тенге)".replace("\u00a0", " ") in text.replace("\u00a0", " ")


def test_purchase_told_once_and_gender_from_the_name(ctx):
    narrative = "17.09.2026 я приобрел(а) у продавца токены и обратился(ась) в поддержку, но ответа не получил(а)."
    text, _ = claim_text(ctx, narrative=narrative)
    assert "мною была совершена покупка" not in text  # 4: the narrative already tells it
    assert "я приобрел у продавца токены и обратился в поддержку, но ответа не получил." in text  # 5


def test_gender_from_the_id_number_when_the_name_does_not_tell(ctx):
    narrative = "17.09.2026 я приобрел(а) токены."
    text, _ = claim_text(ctx, facts={"applicant_name": "Айгерим", "applicant_iin": "900101400123"}, narrative=narrative)
    assert "я приобрела токены." in text


def test_a_real_seller_email_and_address_stay(ctx):
    text, addressee = claim_text(ctx, facts={"seller_email": "support@seller.kz",
                                              "seller_address": "г. Алматы, пр. Достык, 10"})
    assert "E-mail: support@seller.kz" in text and "Адрес: г. Алматы, пр. Достык, 10" in text
    assert addressee["email"] == "support@seller.kz"


def test_services_are_not_called_defective_goods():  # 6: the narrative's rule (the norms go to the lawyer)
    import inspect
    src = inspect.getsource(ai.write_narrative)
    assert "услуга не оказана" in src and "never called a 'товар'" in src


def test_polish_helpers():
    assert tidy_name("антропик") == "Антропик" and tidy_name("тоо ромашка") == "ТОО Ромашка"
    assert tidy_name("Kaspi.kz") == "Kaspi.kz"
    assert tidy_address("алматы сейдимбек 222") == "Алматы, ул. Сейдимбек, 222"
    assert tidy_address("г алматы пр достык 10 кв 5") == "г. Алматы, пр. Достык, 10, кв. 5"
    assert tidy_address("г. Алматы, ул. Абая 1") == "г. Алматы, ул. Абая 1"
    assert gender_from_name("Нурланова Айгерим") == "female" and gender_from_name("Ерлан") == "unknown"
    assert gender_from_id("900101300123", 7, "135", "246") == "male"
    assert gender_from_id("900101400123", 7, "135", "246") == "female"
    assert gender_forms("получил(а), обратился(ась)", "unknown") == "получил(а), обратился(ась)"
    assert number_words(1001, "ru") == "одна тысяча один" and number_words(2000000, "ru") == "два миллиона"
    assert number_words(10352, "kk") == "он мың үш жүз елу екі"
    assert amounts_in_words("10 352,50 KZT", "KZT", "₸", "тенге", "ru") == "10 352,50 ₸"


def test_admin_rebuild_without_a_new_payment(ctx):
    """The first paid claim is made again with the fixes: the owner's «Сохранить» in /ops (facts, rebuild) — no bill."""
    text, _ = claim_text(ctx)
    with ctx.container.session_factory() as s:
        bills = s.scalar(select(func.count()).select_from(Invoice))
        case = s.scalars(select(Case)).first()
        a = case.actions[0]
        a.addressee = {**a.addressee, "email": "client.self@mail.kz"}  # as the old document had it
        cid, before = str(case.id), a.docx_key
        s.commit()
    r = ctx.client.post(f"/v1/admin/cases/{cid}/facts", headers={"X-Admin-Token": "adm"},
                        json={"values": {}, "rebuild": True})
    assert r.status_code == 200 and r.json()["rebuilt"] == 1
    with ctx.container.session_factory() as s:
        a = s.get(Case, uuid.UUID(cid)).actions[0]
        assert a.addressee["email"] is None
        text = docx_text(ctx.container.storage.get(a.docx_key))
    assert "client.self@mail.kz" not in text and "₸ (десять тысяч" in text
    with ctx.container.session_factory() as s:
        assert s.scalar(select(func.count()).select_from(Invoice)) == bills  # no new bill
