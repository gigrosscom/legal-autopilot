"""Published KZ scenarios without a lawyer's sign-off: a neutral note (no "draft" word), no invented norms or deadlines.

A norm reference is either ``TODO`` (the document prints a placeholder) or ``<act title>, статья <N>`` where the act is
a key act of the pack that was opened on adilet.zan.kz (``verified_on`` set). The article itself is checked by a human
against the official text (URL and date in the scenario's YAML comment); this test keeps the format honest.
"""

import re
from pathlib import Path

import pytest

from konsilier.core.packs import load_pack

PACKS = Path(__file__).resolve().parents[3] / "packs"
# the placeholder deadlines of the first two scenarios were replaced by verified norms on 28.09.2026 (REVIEW.md rows 2, 5,
# 12, 16): every deadline now needs a verified norm
LEGACY_PLACEHOLDER_DEADLINES: set[str] = set()
# fields the generic templates read (see scripts/build_kz_templates.py)
# owner's decision 28.09.2026: documents of unsigned scenarios carry this neutral note, never the word "draft"
NEUTRAL_NOTE_RU = "Документ подготовлен IT-сервисом Konsilier AI по вашим данным."
# owner 01.10: the document carries ONE closing line — the AI label (footer); the note above stays in the pack only
AI_LINE_RU = "Подготовлено с помощью ИИ (Konsilier AI)."
DRAFT_WORDS = re.compile(r"черновик|draft|жоба|taslak|مسود", re.IGNORECASE)
TEMPLATE_FIELDS = {"respondent_name", "applicant_name", "applicant_address", "applicant_phone", "problem_description"}


@pytest.fixture(scope="module")
def kz():
    return load_pack(PACKS / "kz", PACKS)


def _verified_titles(kz) -> set[str]:
    return {a.title["ru"] for s in kz.manifest.legal_sources for a in s.key_acts if a.verified_on}


def _ok_ref(ref: str, titles: set[str]) -> bool:
    if ref == "TODO":
        return True
    m = re.fullmatch(r"(.+), статья \d+(-\d+)?", ref)
    return bool(m) and m.group(1) in titles


def test_twenty_published_scenarios_all_drafts(kz):
    published = [sc for sc in kz.scenarios.values() if sc.published]
    assert len(published) == 22  # + kz.gov.inaction_complaint (QA BUG-12), kz.consumer.service_refund (юрист, 01.10)
    for sc in published:
        assert sc.reviewed_at is None, f"{sc.id}: sign-off comes only from a lawyer"
        assert set(sc.languages) == {"ru", "kk"}
        assert sc.taxonomy and kz.coverage.dispute(sc.taxonomy) is not None
        assert "kk" in sc.title and "kk" in sc.summary
        for a in sc.actions:
            if a.kind == "document":
                assert "ru" in a.instructions and "kk" in a.instructions, f"{sc.id}.{a.id}"
                assert len(a.instructions["ru"]) == len(a.instructions["kk"]), f"{sc.id}.{a.id}"


def test_unsigned_note_is_neutral_in_every_pack():
    for pack_dir in sorted(p for p in PACKS.iterdir() if (p / "pack.yaml").exists()):
        note = load_pack(pack_dir, PACKS).manifest.compliance.draft_disclaimer
        assert note, pack_dir.name
        for lang, text in note.items():
            assert not DRAFT_WORDS.search(text), f"{pack_dir.name}/{lang}: {text!r}"
            assert "Konsilier AI" in text, f"{pack_dir.name}/{lang}"
        if "ru" in note:
            assert note["ru"] == NEUTRAL_NOTE_RU, pack_dir.name


def test_norms_and_deadlines_are_verified_or_todo(kz):
    titles = _verified_titles(kz)
    for sc in kz.scenarios.values():
        for a in sc.actions:
            for r in a.norm_refs:
                assert _ok_ref(r, titles), f"{sc.id}.{a.id}: {r!r}"
            if a.deadline and sc.id not in LEGACY_PLACEHOLDER_DEADLINES:
                assert a.deadline.norm_ref != "TODO" and _ok_ref(a.deadline.norm_ref, titles), \
                    f"{sc.id}.{a.id}: a deadline needs a verified norm"


def test_generic_template_fields_are_asked(kz):
    for sc in kz.scenarios.values():
        uses_generic = any(a.template and "/generic/" in a.template for a in sc.actions)
        if uses_generic:
            names = {f.name for f in sc.intake}
            assert TEMPLATE_FIELDS <= names, f"{sc.id}: {TEMPLATE_FIELDS - names}"


def test_addressees_exist(kz):
    ids = set(kz.coverage.forums)
    for sc in kz.scenarios.values():
        for a in sc.actions:
            if a.addressee and a.addressee.forum:
                assert a.addressee.forum in ids
            if a.addressee and a.addressee.authority:
                assert a.addressee.authority in kz.manifest.authorities


def test_evidence_kinds_are_translated(kz):
    for sc in kz.scenarios.values():
        for f in sc.intake:
            for kind in f.evidence_kinds:
                for lang in ("ru", "kk"):
                    assert kz.i18n[lang]["evidence"].get(kind), f"{sc.id}: evidence.{kind} [{lang}]"
