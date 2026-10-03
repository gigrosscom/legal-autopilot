"""PM 03.10, quality pilot (family law): a divorce was asked «Пришлите … чек или договор, гарантийный талон или акт …
— я сам возьму из них даты и суммы»: the request for documents was the consumer one for every case without a set of
its own. Now it is built from the scenario's own documents (for the universal path — its dispute route's, routes.yaml
`documents`), and a case not about money is asked in neutral words. Invariants for the whole class:
1) every scenario's request names no document of another scenario's set;
2) receipts, warranty cards, acts and sums are never named in a case that is not about money;
3) every document a route lists has its label in ru and kk."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from konsilier.api.chat import documents_line, intake_note
from konsilier.core.generic import GenericRef
from konsilier.core.models import Case
from konsilier.core.packs import PackRegistry

KZ = PackRegistry.load(Path(__file__).resolve().parents[3] / "packs").pack("KZ")
LABELS = {lang: {k: str(v).lower() for k, v in (KZ.i18n.get(lang, {}).get("evidence") or {}).items()}
          for lang in ("ru", "kk")}
MONEY_WORDS = re.compile(r"(?<!\w)чек|гарантийн|(?<!\w)акт(?:а|ом|ы)?(?!\w)|сумм|чектер|сома", re.IGNORECASE)


def _line(ctx, scenario_id: str, lang: str, dispute: str | None = None) -> tuple[str, list[str], bool]:
    case = Case(language=lang, jurisdiction="KZ", scenario_id=scenario_id, facts={}, skipped_fields=[],
                taxonomy={"dispute_id": dispute} if dispute else {})
    note = intake_note(ctx.container, case, lang)
    kinds, money = ctx.container.engine.documents_to_ask(case)
    return documents_line(KZ, lang, note), kinds, money


@pytest.mark.parametrize("lang", ["ru", "kk"])
@pytest.mark.parametrize("sid", sorted(KZ.scenarios), ids=lambda s: s)
def test_a_scenario_asks_only_for_its_own_documents(ctx, sid, lang):
    text, kinds, money = _line(ctx, sid, lang)
    own = {LABELS[lang].get(k, "") for k in kinds}
    foreign = [label for k, label in LABELS[lang].items()
               if k not in kinds and k not in ("other", "id_document") and label and label in text.lower()
               and not any(label in o for o in own)]
    assert not foreign, (sid, foreign, text)
    if not money:  # receipts and sums only where the scenario's own documents name them
        rest = text.lower()
        for label in sorted(own, key=len, reverse=True):
            rest = rest.replace(label, " ") if label else rest
        assert not MONEY_WORDS.search(rest), (sid, text)


@pytest.mark.parametrize("lang", ["ru", "kk"])
def test_a_divorce_on_the_universal_path_asks_for_family_documents(ctx, lang):
    sid = GenericRef("KZ", "family.divorce", "spouse", "kz.court.juvenile").scenario_id
    text, kinds, money = _line(ctx, sid, lang, dispute="family.divorce")
    assert not money and "marriage_certificate" in kinds
    assert LABELS[lang]["marriage_certificate"] in text.lower()
    assert not MONEY_WORDS.search(text), text


@pytest.mark.parametrize("lang", ["ru", "kk"])
def test_without_a_set_the_request_is_neutral(ctx, lang):
    sid = GenericRef("KZ", "family.alimony", "parent", "kz.court.juvenile").scenario_id
    case = Case(language=lang, jurisdiction="KZ", scenario_id=sid, facts={}, skipped_fields=[], taxonomy={})
    text = documents_line(KZ, lang, {"documents_to_ask": [], "money": False})
    assert not MONEY_WORDS.search(text), text
    assert case.scenario_id


def test_every_route_document_has_its_label():
    for key, route in KZ.coverage.routes.items():
        for kind in route.documents:
            for lang in ("ru", "kk"):
                assert LABELS[lang].get(kind), (key, kind, lang)
