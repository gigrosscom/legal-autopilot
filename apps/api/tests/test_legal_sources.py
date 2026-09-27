"""Official legal databases per pack (docs/legal-sources.md): data shape and public exposure."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from konsilier.core.packs import LegalSource, PackRegistry

REPO = Path(__file__).resolve().parents[3]
PACKS = sorted(p.parent.name for p in (REPO / "packs").glob("*/pack.yaml"))


@pytest.fixture(scope="module")
def registry() -> PackRegistry:
    return PackRegistry.load(REPO / "packs")


@pytest.mark.parametrize("cc", PACKS)
def test_every_pack_has_an_official_legislation_source(registry, cc):
    pack = registry.pack(cc)
    if pack.manifest.status == "test":
        pytest.skip("test fixture pack")
    sources = pack.manifest.legal_sources
    legislation = [s for s in sources if s.kind == "legislation"]
    assert legislation, f"{cc}: no legislation source"
    assert any(s.url.startswith("https://") for s in legislation), f"{cc}: legislation source must be https"
    for s in sources:
        assert s.url.startswith("https://"), f"{cc}/{s.id}: use https"
        assert s.name.get("en") and s.name.get("ru"), f"{cc}/{s.id}: name needs en and ru"
        assert s.languages and s.operator
        assert s.api is None or s.api == "unknown" or s.api.startswith("https://")
        assert s.verified_on is None or s.verified_on <= date.today()


def test_legal_source_is_strict():
    base = {"id": "x", "name": {"en": "X"}, "url": "https://x.example", "operator": "O",
            "kind": "legislation", "languages": ["en"]}
    assert LegalSource.model_validate(base).access == "web"
    for bad in ({"kind": "blog"}, {"access": "scrape"}, {"url": "ftp://x"}, {"name": {"ru": "Х"}}, {"extra": 1}):
        with pytest.raises(ValidationError):
            LegalSource.model_validate({**base, **bad})


def test_coverage_endpoint_lists_legal_sources(ctx):
    cov = ctx.client.get("/v1/coverage?lang=ru").json()
    kz = next(c for c in cov["countries"] if c["country"] == "KZ")
    adilet = next(s for s in kz["legal_sources"] if s["id"] == "adilet")
    assert adilet["url"].startswith("https://adilet.zan.kz")
    assert adilet["name"] == "ИПС «Әділет»" and adilet["kind"] == "legislation"
