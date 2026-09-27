"""Coverage data: taxonomy, forum registry, document types, routing — schemas and cross-validation."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from konsilier.core.coverage import CoverageValidationError, global_taxonomy, load_coverage
from konsilier.core.coverage.schema import Forum
from konsilier.core.packs import PackRegistry, PackValidationError

REPO = Path(__file__).resolve().parents[3]


def _forum(**over):
    base = {
        "id": "xx.court.main", "type": "court", "name": {"en": "Main court"},
        "accepts": [{"branches": ["civil"]}], "document_types": ["lawsuit"],
        "submission": [{"kind": "in_person"}], "languages": ["en"], "legal_effect": "binding", "source": "test",
    }
    base.update(over)
    return base


def test_global_taxonomy_is_valid_and_country_neutral():
    tax = global_taxonomy()
    ids = [d.id for b in tax.branches for d in b.disputes]
    assert len(ids) == len(set(ids))
    assert "criminal.defence" in ids and "labor.dismissal" in ids
    for b in tax.branches:
        assert {"ru", "kk", "en"} <= set(b.title)


def test_kz_registry_loads_and_nothing_is_marked_verified():
    cov = PackRegistry.load(REPO / "packs").pack("KZ").coverage
    assert cov.has_registry
    assert all(not f.verified for f in cov.forums.values())  # no lawyer sign-off yet
    assert all(status == "TODO" for kind, _, status, _ in cov.review_rows() if kind in ("forum", "document"))


def test_candidates_and_escalation_come_from_data():
    cov = PackRegistry.load(REPO / "packs").pack("KZ").coverage
    wages = cov.dispute("labor.unpaid_wages")
    ids = {f.id for f in cov.candidate_forums(wages, "employee")}
    assert "kz.labor_inspection" in ids and "kz.court.appeal" not in ids  # appeal courts only via escalation
    assert [f.id for f in cov.escalation_chain("kz.labor_inspection", wages, "employee")] == \
        ["kz.court.district", "kz.court.appeal"]
    crime = cov.dispute("criminal.crime_report")
    assert {f.id for f in cov.candidate_forums(crime, "victim")} == {"kz.police"}


def test_defence_is_always_lawyer_only():
    cov = PackRegistry.load(REPO / "packs").pack("KZ").coverage
    defence = cov.dispute("criminal.defence")
    assert cov.is_lawyer_only(defence, "suspect")
    assert cov.candidate_forums(defence, "suspect") == []


def test_religious_bodies_are_not_a_forum_type():
    with pytest.raises(ValueError):
        Forum.model_validate(_forum(type="religious"))

def _pack_with(tmp_path: Path, forums: list[dict], routing: dict | None = None) -> Path:
    root = tmp_path / "packs"
    shutil.copytree(REPO / "packs" / "kz", root / "kz")
    (root / "kz" / "forums" / "registry.yaml").write_text(yaml.safe_dump({"forums": forums}, allow_unicode=True))
    if routing is not None:
        (root / "kz" / "routing.yaml").write_text(yaml.safe_dump(routing))
    return root


def test_validation_rejects_broken_references_and_cycles(tmp_path):
    a = _forum(id="kz.a.one", name={"ru": "A", "kk": "A"}, appeals_to=["kz.b.two"], languages=["ru"])
    b = _forum(id="kz.b.two", name={"ru": "B", "kk": "B"}, appeals_to=["kz.a.one"], languages=["ru"])
    bad = _forum(id="kz.c.three", name={"ru": "C", "kk": "C"}, appeals_to=["kz.nowhere"],
                 accepts=[{"branches": ["astrology"]}], languages=["ru"])
    root = _pack_with(tmp_path, [a, b, bad], routing={"lawyer_only": ["no.such"]})
    with pytest.raises(PackValidationError) as e:
        PackRegistry.load(root)
    msg = str(e.value)
    assert "escalation cycle" in msg
    assert "unknown forum kz.nowhere" in msg
    assert "unknown branch astrology" in msg
    assert "lawyer_only refers to unknown no.such" in msg


def test_forum_names_need_every_pack_language(tmp_path):
    root = _pack_with(tmp_path, [_forum(id="kz.x.y", name={"ru": "Только ru"}, languages=["ru"])])
    with pytest.raises(PackValidationError, match="missing languages"):
        PackRegistry.load(root)


def test_pack_without_coverage_files_still_loads(tmp_path):
    root = tmp_path / "packs" / "kz"
    shutil.copytree(REPO / "packs" / "kz", root)
    for name in ("forums", "documents"):
        shutil.rmtree(root / name)
    for name in ("routing.yaml", "taxonomy.yaml"):
        (root / name).unlink()
    cov = load_coverage(root, root.parent, "KZ", ("ru", "kk"))
    assert not cov.has_registry and cov.forums == {}


def test_local_taxonomy_ids_need_country_prefix(tmp_path):
    root = tmp_path / "packs"
    shutil.copytree(REPO / "packs" / "kz", root / "kz")
    (root / "kz" / "taxonomy.yaml").write_text(yaml.safe_dump({"add": [{
        "id": "labor.local_thing", "title": {"ru": "x"}, "applicant_roles": ["employee"]}]}))
    with pytest.raises(CoverageValidationError, match="must start with 'kz.'"):
        load_coverage(root / "kz", root, "KZ", ("ru", "kk"))


def test_messenger_channels_need_an_official_link_and_its_source():
    from konsilier.core.coverage.schema import SubmissionChannel
    ok = SubmissionChannel.model_validate({"kind": "whatsapp", "url": "https://wa.me/77001234567",
                                           "source": "https://www.gov.kz/memleket/entities/example"})
    assert ok.kind == "whatsapp"
    SubmissionChannel.model_validate({"kind": "telegram", "url": "https://t.me/official_body",
                                      "source": "https://www.gov.kz/memleket/entities/example"})
    for bad in ({"kind": "whatsapp", "url": "https://wa.me/77001234567"},  # no source
                {"kind": "whatsapp", "url": "+7 700 123 45 67", "source": "x"},  # not a wa.me link
                {"kind": "telegram", "url": "https://t.me/a", "source": "x"}):
        with pytest.raises(ValueError):
            SubmissionChannel.model_validate(bad)
