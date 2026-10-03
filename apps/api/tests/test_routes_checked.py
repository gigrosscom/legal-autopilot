"""ZANN 03.10: routes for the universal path, checked on old.adilet.zan.kz — the chat's steps (R-35) and the card follow
them. Each step names its norm; a route without a checked norm is not added."""

from __future__ import annotations

from pathlib import Path

from konsilier.core.packs import PackRegistry

COV = PackRegistry.load(Path(__file__).parents[3] / "packs").pack("KZ").coverage


def test_new_routes_and_their_norms():
    expect = {
        "administrative.fine_appeal": ("kz.gov.superior", "КоАП РК, ст. 826-1"),
        "criminal.crime_report": ("kz.police", "УПК РК, ст. 180 ч. 1 п. 1"),
        "criminal.police_inaction": ("kz.prosecutor", "УПК РК, ст. 105 ч. 1"),
        "family.divorce": ("kz.court.district", "КоБС РК, ст. 17 п. 1"),
        "tax.assessment_dispute": ("kz.gov.superior", "Налоговый кодекс РК 2025, ст. 191"),
        "inheritance.acceptance": ("kz.notary", "ГК РК (Особенная часть), ст. 1072-1"),
    }
    for dispute, (forum, norm) in expect.items():
        first = COV.routes[dispute].steps[0]
        assert first.forum == forum and first.norm.startswith(norm), dispute


def test_every_route_step_names_a_norm():
    for key, route in COV.routes.items():
        for step in route.steps:
            assert step.norm.strip(), key
