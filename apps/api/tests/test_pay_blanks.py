"""PM 02.10 (browser run, iPhone 390): 1) the payment window read «Услуга: Документ» — the scenario's document title
is back («Претензия продавцу…»); 2) «Оплатить» was active while the draft showed «Адрес: [Адрес продавца]» — every
required blank (the other side's name and address too) is asked before paying or making the document. Only the
other side's BIN/IIN may stay blank: a person often cannot know it."""

from __future__ import annotations

from .test_draft_prefill import to_draft


def _blanks(api, cid):
    return {b["field"] for b in api.get(f"/v1/cases/{cid}/draft").json()["blanks"]}


def test_payment_asks_every_required_blank_but_the_other_sides_id(ctx):
    api, case = to_draft(ctx)
    cid = case["id"]
    blanks = _blanks(api, cid)
    assert blanks, "the story left blanks in the draft"
    r = api.c.post(f"/v1/cases/{cid}/payment", headers=api.h, json={"purpose": "document"})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "applicant_data_required"
    asked = {f["field"]: f for f in r.json()["detail"]["fields"]}
    assert set(asked) <= blanks
    assert not [n for n, f in asked.items() if not f["own"] and (n.endswith("_bin") or n.endswith("_iin"))]


def test_the_other_sides_address_must_be_filled_before_paying(ctx):
    api, case = to_draft(ctx)
    cid = case["id"]
    r = api.c.post(f"/v1/cases/{cid}/payment", headers=api.h, json={"purpose": "document"})
    fields = {f["field"]: f for f in r.json()["detail"]["fields"]}
    theirs = [n for n, f in fields.items() if not f["own"]]
    assert theirs, fields  # e.g. «Адрес продавца», «Продавец»
    # a document paid by credits or a plan is not made with the blank either
    r2 = api.c.post(f"/v1/cases/{cid}/actions/next", headers=api.h)
    assert r2.status_code == 422 and r2.json()["detail"]["code"] == "applicant_data_required"
    by_type = {"date": "12.08.2026", "money": "150000", "phone": "+7 701 123 45 67", "address": "г. Алматы, ул. Абая, 10"}
    values = {n: by_type.get(f["type"]) or ("г. Алматы, ул. Абая, 10" if n.endswith("address")
                                            else "880101300123" if n.endswith("iin") else "ТОО «Техномир»")
              for n, f in fields.items()}
    out = api.c.post(f"/v1/cases/{cid}/facts", headers=api.h, json={"values": values})
    assert out.status_code == 200, out.json()
    r3 = api.c.post(f"/v1/cases/{cid}/payment", headers=api.h, json={"purpose": "document"})
    assert r3.status_code == 200, r3.json()
    left = {b["field"] for b in api.get(f"/v1/cases/{cid}/draft").json()["blanks"]}
    # only the other side's ID and free text (written from the story) may stay blank
    assert all(n.endswith(("_bin", "_iin")) or n.endswith("description") for n in left), left


def test_the_payment_window_names_the_document(ctx):
    api, case = to_draft(ctx)
    pay = api.get(f"/v1/cases/{case['id']}").json()["payment"]
    assert pay["title"] and pay["title"] != "Документ"
    assert pay["title"].startswith("Претензия")
