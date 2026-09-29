"""«Как подать»: the filing card of a ready document — addressee, the terms, the ways and the online steps by device."""

from datetime import date

import pytest
from pydantic import ValidationError

from konsilier.core.filing import filing_view
from konsilier.core.packs import PackRegistry
from konsilier.core.scenario.schema import FilingDeadlineSpec, FilingSpec

from .conftest import REPO
from .test_e2e import run_intake
from .test_roadmap import ANSWERS, new_refund_case


@pytest.fixture(scope="module")
def kz():
    return PackRegistry.load(REPO / "packs").pack("KZ")


def _with_filing(sc, action_id: str, filing: FilingSpec):
    spec = sc.action(action_id).model_copy(update={"filing": filing})
    return sc.model_copy(update={"actions": tuple(spec if a.id == action_id else a for a in sc.actions)}), spec


SELLER = {"kind": "business", "name": "ТОО «Техномир»", "address": "Алматы, пр. Абая 10", "email": None}


def test_response_term_is_known_before_filing(kz):
    sc = kz.scenarios["kz.consumer.refund"]
    out = filing_view(kz, sc, sc.action("claim_to_seller"), lang="ru", addressee=SELLER, facts={})
    assert out["to"] == {"name": "ТОО «Техномир»", "address": "Алматы, пр. Абая 10", "email": None}
    assert out["response"] == {"days": 10, "unit": "calendar", "verified": True,
                               "norm_ref": "Закон Республики Казахстан «О защите прав потребителей», статья 42-4"}
    # a claim to the seller: on paper or by e-mail, as the action channel says
    assert [w["kind"] for w in out["ways"]] == ["in_person", "post", "email"]
    assert "2 экземпляра" in out["ways"][0]["hint"] and "отметку о принятии" in out["ways"][0]["hint"]
    assert "уведомлением" in out["ways"][1]["hint"]
    assert out["online"] is None


def test_no_filing_data_means_lawyer_will_confirm(kz):
    sc = kz.scenarios["kz.consumer.refund"]
    out = filing_view(kz, sc, sc.action("claim_to_seller"), lang="ru", addressee=SELLER, facts={})
    # nothing about the filing term or signature is in the data: the client shows «уточнит юрист»
    assert out["file_by"] is None
    assert out["signature"] is None and out["signature_text"] is None


def test_unknown_response_norm_is_not_shown_as_verified(kz):
    sc = kz.scenarios["kz.consumer.refund"]
    spec = sc.action("claim_to_seller")
    spec = spec.model_copy(update={"deadline": spec.deadline.model_copy(update={"norm_ref": "TODO"})})
    out = filing_view(kz, sc, spec, lang="ru", addressee=SELLER, facts={})
    assert out["response"]["days"] == 10 and out["response"]["norm_ref"] is None
    assert out["response"]["verified"] is False


def test_file_by_is_counted_from_a_fact(kz):
    sc, spec = _with_filing(kz.scenarios["kz.consumer.refund"], "claim_to_seller", FilingSpec(
        deadline=FilingDeadlineSpec(calendar_days=10, from_field="purchase_date", norm_ref="Норма X", verified=True),
        signature="handwritten"))
    out = filing_view(kz, sc, spec, lang="ru", addressee=SELLER, facts={"purchase_date": "2026-09-01"},
                      today=date(2026, 9, 20))
    fb = out["file_by"]
    assert fb["date"] == "2026-09-11" and fb["days"] == 10 and fb["unit"] == "calendar"
    assert fb["norm_ref"] == "Норма X" and fb["verified"] is True and fb["overdue"] is True
    assert fb["since"] and "«" in fb["since"]  # "с даты «<field label>»"
    assert out["signature"] == "handwritten" and out["signature_text"] == "Собственноручная подпись на бумаге"

    # business days skip weekends; 2026-09-04 is a Friday
    sc, spec = _with_filing(sc, "claim_to_seller", FilingSpec(
        deadline=FilingDeadlineSpec(business_days=1, from_field="purchase_date",
                                    from_text={"ru": "со дня покупки"})))
    fb = filing_view(kz, sc, spec, lang="ru", addressee=SELLER, facts={"purchase_date": "04.09.2026"})["file_by"]
    assert fb["date"] == "2026-09-07" and fb["since"] == "со дня покупки"
    assert fb["verified"] is False and fb["norm_ref"] is None


def test_file_by_without_the_start_fact_is_described_in_words(kz):
    sc, spec = _with_filing(kz.scenarios["kz.consumer.refund"], "claim_to_seller", FilingSpec(
        deadline=FilingDeadlineSpec(calendar_days=30, from_field="purchase_date",
                                    from_text={"ru": "со дня вручения решения"})))
    fb = filing_view(kz, sc, spec, lang="ru", addressee=SELLER, facts={})["file_by"]
    assert fb["date"] is None and fb["days"] == 30 and fb["since"] == "со дня вручения решения"


def test_filing_ways_from_the_data_replace_derived_ones(kz):
    sc, spec = _with_filing(kz.scenarios["kz.consumer.refund"], "claim_to_seller", FilingSpec(ways=("post",)))
    out = filing_view(kz, sc, spec, lang="ru", addressee=SELLER, facts={})
    assert [w["kind"] for w in out["ways"]] == ["post"]


def test_eotinish_steps_by_device(kz):
    sc = kz.scenarios["kz.consumer.refund"]
    spec = sc.action("complaint_consumer_authority")
    addressee = {"kind": "authority", "name": "Департамент", "address": "", "email": None,
                 "submit_url": "https://eotinish.kz"}
    out = filing_view(kz, sc, spec, lang="ru", addressee=addressee, facts={})
    assert out["response"]["days"] == 15 and out["response"]["unit"] == "business"
    assert [w["kind"] for w in out["ways"]] == ["online"]
    online = out["online"]
    assert online["portal"] == "eotinish.kz" and online["phone_ok"] is True
    assert any("eGov Mobile" in s for s in online["phone"])
    assert any("NCALayer" in s for s in online["desktop"]) and any("ЭЦП" in s for s in online["desktop"])
    assert any("Департамент" in s for s in online["phone"])  # the addressee is filled in
    kk = filing_view(kz, sc, spec, lang="kk", addressee=addressee, facts={})["online"]
    assert kk["phone"] and kk["phone"] != online["phone"]


def test_court_portal_is_better_from_a_computer(kz):
    from konsilier.core.generic import GenericRef, build_generic_scenario

    ref = GenericRef("KZ", "labor.unpaid_wages", "employee", "kz.court.district")
    sc = build_generic_scenario(kz, ref)
    forum = kz.coverage.forums["kz.court.district"]
    spec = sc.actions[0]
    out = filing_view(kz, sc, spec, lang="ru", facts={}, forum=forum,
                      addressee={"name": "Районный суд", "submit_url": "https://office.sud.kz"})
    assert [w["kind"] for w in out["ways"]] == ["online", "in_person"]
    assert out["online"]["phone_ok"] is False
    assert any("с компьютера" in s for s in out["online"]["phone"])
    assert any("NCALayer" in s for s in out["online"]["desktop"])
    assert out["response"] is None  # the registry has no term for courts yet → «уточнит юрист»


def test_filing_block_is_validated(kz):
    with pytest.raises(ValidationError):
        FilingDeadlineSpec(calendar_days=10, business_days=5)
    with pytest.raises(ValidationError, match="norm_ref"):
        FilingDeadlineSpec(calendar_days=10, verified=True)
    sc = kz.scenarios["kz.consumer.refund"]
    raw = sc.model_dump(by_alias=True, mode="json")
    raw["actions"][0]["filing"] = {"deadline": {"calendar_days": 10, "from_field": "no_such_field"}}
    with pytest.raises(ValidationError, match="from_field"):
        type(sc).model_validate(raw)
    raw["actions"][0]["filing"] = {"deadline": {"calendar_days": 10, "from_field": "seller_name"}}
    with pytest.raises(ValidationError, match="must be a date"):
        type(sc).model_validate(raw)
    raw["actions"][0]["filing"] = {"deadline": {"calendar_days": 10, "from_field": "purchase_date"},
                                   "signature": "either", "ways": ["in_person", "post"]}
    assert type(sc).model_validate(raw).actions[0].filing.signature == "either"


def test_case_view_carries_the_filing_card(ctx):
    api, cid = new_refund_case(ctx)
    run_intake(api, cid, {**ANSWERS, "evidence": "пропустить", "identity_document": "пропустить"})
    a = api.post(f"/v1/cases/{cid}/actions/next")["case"]["actions"][0]
    assert a["submitted_at"] is None and a["deadline"] is None  # not filed yet …
    f = a["filing"]
    assert f["response"]["days"] == 10  # … but the term to answer is already known
    assert f["to"]["name"] == "ТОО «Техномир»" and f["to"]["address"] == "Алматы, пр. Абая 10"
    assert f["file_by"] is None
    assert {w["kind"] for w in f["ways"]} == {"in_person", "post", "email"}
