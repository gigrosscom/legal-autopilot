"""egov.kz certificates helper: links only, filtered by the case's branch of law."""

from __future__ import annotations

from pathlib import Path

from konsilier.core.packs import load_pack

from .test_e2e import web_user

PACKS = Path(__file__).resolve().parents[3] / "packs"


def test_kz_catalogue_is_valid_and_official():
    kz = load_pack(PACKS / "kz", PACKS)
    ids = [g.id for g in kz.gov_services.services]
    assert len(ids) == len(set(ids))
    for g in kz.gov_services.services:
        assert g.url.startswith(("https://egov.kz/", "https://data.egov.kz/")), g.url
        assert {"ru", "kk"} <= set(g.title)


def test_case_gets_services_for_its_branch(ctx):
    api = web_user(ctx)
    cid = api.post("/v1/cases", expect=201, json={
        "text": "Купил телефон в магазине, через неделю сломался, деньги не возвращают 150000", "country": "KZ"})["case"]["id"]
    ids = {g["id"] for g in api.get(f"/v1/cases/{cid}/gov-services").json()}
    assert "legal_entity_info" in ids and "credit_report" in ids  # consumer branch
    assert "birth_certificate_repeat" not in ids  # family only
    other = web_user(ctx)
    assert ctx.client.get(f"/v1/cases/{cid}/gov-services", headers=other.h).status_code == 404
