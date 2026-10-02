"""«Куда подать» (PM 02.10, owner's screenshots): the pre-trial step first, then the court, optional ways last; «the court
where your case already is» only when the person says so; concrete terms and norms instead of «уточнит юрист»."""

from __future__ import annotations

from pathlib import Path

from konsilier.core import qualifier, safety
from konsilier.core.packs import PackRegistry

REPO = Path(__file__).resolve().parents[3]


def _cov():
    return PackRegistry.load(REPO / "packs").pack("KZ").coverage


def test_private_debt_order_and_no_pending_court():
    cov = _cov()
    debt = cov.dispute("civil.debt")
    ids = [f.id for f in cov.candidate_forums(debt, "claimant")]
    assert ids == ["kz.counterparty.claim", "kz.court.district", "kz.mediation"]
    with_pending = [f.id for f in cov.candidate_forums(debt, "claimant", pending=True)]
    assert with_pending[-1] == "kz.court.pending"


def test_pending_comes_from_the_story():
    cov = _cov()
    assert safety.matter_pending(cov, "Суд уже назначил судебное заседание, номер дела 7599-26")
    assert not safety.matter_pending(cov, "Дал знакомому в долг по расписке, он не возвращает")
    route = qualifier.route_universal(cov, {"dispute_id": "civil.debt", "role": "claimant", "confidence": 0.9},
                                      pending=True)
    assert "pending" in route.flags and route.forums[-1].id == "kz.court.pending"


def test_debt_hints_cite_the_norms_and_every_hint_key_is_known():
    cov = _cov()
    known = set(cov.disputes) | {d.branch for d in cov.disputes.values()}
    for f in cov.forums.values():
        assert set(f.hints) <= known and set(f.mandatory_for) <= known, f.id
        for text in f.hints.values():
            assert {"ru", "kk"} <= set(text) and "уточнит юрист" not in text["ru"]
    claim = cov.forums["kz.counterparty.claim"].hints["civil.debt"]["ru"]
    assert "30 дней" in claim and "ст. 722" in claim
    court = cov.forums["kz.court.district"].hints["civil.debt"]["ru"]
    assert "ст. 29" in court and "3 года" in court and "ст. 178" in court and "ст. 135" in court


def test_forum_option_shows_pretrial_label_and_hint(ctx):
    engine = ctx.container.engine
    pack = PackRegistry.load(REPO / "packs").pack("KZ")
    cov = pack.coverage
    debt = cov.dispute("civil.debt")
    claim = engine.forum_option(pack, cov.forums["kz.counterparty.claim"], "ru", debt)
    assert claim["pretrial"] == "voluntary" and claim["deadline_known"] and "30 дней" in claim["hint"]
    court = engine.forum_option(pack, cov.forums["kz.court.district"], "ru", debt)
    assert court["pretrial"] is None and court["deadline_known"] and "уточнит юрист" not in court["name"]
