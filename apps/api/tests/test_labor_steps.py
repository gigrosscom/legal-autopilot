"""Owner's screenshots 02.10 (Невыплата зарплаты): «Как подать» with the terms instead of «уточнит юрист», steps with a
bold heading each, no empty «()» when the employer's name is not known yet."""

from __future__ import annotations

from pathlib import Path

from konsilier.core.engine import _tidy
from konsilier.core.filing import filing_view
from konsilier.core.packs import PackRegistry

REPO = Path(__file__).resolve().parents[3]


def test_empty_addressee_brackets_are_dropped():
    assert _tidy("**Вручите работодателю ().** Один экземпляр отдайте.") == \
        "**Вручите работодателю.** Один экземпляр отдайте."
    assert _tidy("Вручите работодателю (ТОО «Ромашка»).") == "Вручите работодателю (ТОО «Ромашка»)."


def test_labor_first_step_has_terms_and_headed_steps():
    pack = PackRegistry.load(REPO / "packs").pack("KZ")
    for sid in ("kz.labor.unpaid_wages", "kz.labor.final_settlement", "kz.labor.dismissal"):
        sc = pack.scenarios[sid]
        spec = sc.actions[0]
        view = filing_view(pack, sc, spec, lang="ru", addressee={}, facts={"event_date": "01.09.2026"})
        assert view["response"]["days"] == 15 and "159" in view["response"]["norm_ref"], sid
        assert view["file_by"]["norm_ref"].endswith("статья 160") and view["file_by"]["date"], sid
        assert view["signature"] == "either" and view["to"]["name"], sid  # «Работодатель», not «уточнит юрист»
        for lang in ("ru", "kk"):
            steps = spec.instructions[lang]
            assert all(s.startswith("**") for s in steps), (sid, lang)
            assert not any("уточнит юрист" in s or "можно подать и туда" in s for s in steps), sid


def test_demand_goes_to_the_head_for_the_commission_or_himself(ctx):
    """Owner 02.10: the person cannot know whether a conciliation commission exists — the demand is addressed to the
    head: for the commission, or for the head himself if there is none. No question about the commission."""
    pack = PackRegistry.load(REPO / "packs").pack("KZ")
    for sid in ("kz.labor.unpaid_wages", "kz.labor.final_settlement", "kz.labor.dismissal"):
        spec = pack.scenarios[sid].actions[0]
        assert "{name}" in spec.addressee.heading["ru"] and "согласительной комиссии" in spec.addressee.heading["ru"]
        assert pack.localized(spec.demands, "ru").startswith("рассмотреть настоящее")
    assert "head of the employer" in pack.manifest.chat_rules
