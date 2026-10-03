"""Stage 5 pilot scenarios: present as drafts, never published, never carrying invented deadlines or norms."""

from pathlib import Path

import pytest

from konsilier.core.packs import load_pack

PACKS = Path(__file__).resolve().parents[3] / "packs"
DRAFTS = ("kz.labor.unpaid_wages", "kz.administrative.fine_appeal", "kz.family.alimony")
# fields the generic templates read (see scripts/build_kz_templates.py)
TEMPLATE_FIELDS = {"respondent_name", "applicant_name", "applicant_address", "applicant_phone", "problem_description"}


@pytest.fixture(scope="module")
def kz():
    return load_pack(PACKS / "kz", PACKS)


@pytest.mark.parametrize("sid", DRAFTS)
def test_pilot_is_unpublished_draft(kz, sid):
    sc = kz.scenarios[sid]
    assert sc.published is False
    assert sc.reviewed_at is None
    assert sc.taxonomy and kz.coverage.dispute(sc.taxonomy) is not None


@pytest.mark.parametrize("sid", DRAFTS)
def test_pilot_has_no_invented_deadlines_or_norms(kz, sid):
    for a in kz.scenarios[sid].actions:
        assert a.deadline is None, f"{sid}.{a.id}: deadlines come only from a lawyer"
        assert all(r == "TODO" for r in a.norm_refs)


@pytest.mark.parametrize("sid", DRAFTS)
def test_pilot_intake_covers_template_fields(kz, sid):
    names = {f.name for f in kz.scenarios[sid].intake}
    assert TEMPLATE_FIELDS <= names


@pytest.mark.parametrize("sid", DRAFTS)
def test_pilot_forums_exist_in_registry(kz, sid):
    ids = set(kz.coverage.forums)
    for a in kz.scenarios[sid].actions:
        if a.addressee and a.addressee.forum:
            assert a.addressee.forum in ids
