"""Jurisdiction packs: everything country-specific, loaded from ``packs/<cc>/`` as data."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

import yaml

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .coverage import Coverage, CoverageValidationError, load_coverage
from .generic import GenericRef, build_generic_scenario
from .scenario import Scenario, ScenarioValidationError, load_scenario_file

log = logging.getLogger(__name__)

Localized = dict[str, str]


class PackValidationError(Exception):
    pass


class AuthoritySpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: Localized
    submit_url: str | None = None
    address: Localized = Field(default_factory=dict)
    email: str | None = None
    norm_ref: str = "TODO"


class ComplianceSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    ai_label: Localized  # mandatory mark on every document and result screen
    draft_disclaimer: Localized
    service_disclaimer: Localized


class LegalSource(BaseModel):
    """An official legal database of the country: we link to and cite it, never mirror it."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str = Field(pattern=r"^[a-z0-9_]+$")
    name: Localized  # at least ``en``; ``ru`` and the local language where helpful
    url: str = Field(pattern=r"^https?://")
    operator: str
    kind: Literal["legislation", "case_law", "gazette", "registry"]
    languages: tuple[str, ...]
    access: Literal["web", "api", "bulk"] = "web"
    api: str | None = None  # docs URL of an official API, or "unknown"; never guessed
    terms_url: str | None = None
    reuse_note: str | None = None
    verified_on: date | None = None  # set only when the URL and operator were confirmed online

    @field_validator("name")
    @classmethod
    def _name_en(cls, v: Localized) -> Localized:
        if "en" not in v:
            raise ValueError("legal source name needs an 'en' entry")
        return v


class PackManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    country: str
    name: Localized
    currency: str
    timezone: str
    languages: tuple[str, ...]
    default_language: str
    holidays: tuple[date, ...] = ()
    reminder_before_days: tuple[int, ...] = (2, 0)
    authorities: dict[str, AuthoritySpec] = Field(default_factory=dict)
    compliance: ComplianceSpec
    status: Literal["live", "test", "planned"] = "live"  # planned: skeleton, no cases accepted
    legal_sources: tuple[LegalSource, ...] = ()  # official legislation / case-law databases (docs/legal-sources.md)

    @field_validator("legal_sources")
    @classmethod
    def _unique_sources(cls, v: tuple[LegalSource, ...]) -> tuple[LegalSource, ...]:
        ids = [s.id for s in v]
        if len(ids) != len(set(ids)):
            raise ValueError("legal_sources ids must be unique")
        return v

    @field_validator("country")
    @classmethod
    def _cc(cls, v: str) -> str:
        if len(v) != 2 or not v.isalpha() or not v.isupper():
            raise ValueError("country must be an ISO 3166-1 alpha-2 code in upper case")
        return v

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: str) -> str:
        ZoneInfo(v)
        return v


class AgreementTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    title: dict[str, str]
    body: dict[str, tuple[str, ...]]


class AgreementSet(BaseModel):
    """Customer ↔ lawyer documents (agreements.yaml): data, reviewed by a lawyer like scenarios."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    reviewed_at: date | None = None
    owner: str
    lawyer_kinds: dict[str, dict[str, str]] = Field(default_factory=dict)
    templates: dict[str, AgreementTemplate]
    footer: dict[str, dict[str, str]] = Field(default_factory=dict)


class GovService(BaseModel):
    """A certificate the person gets themselves on an official portal (we only link; no integration)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str
    title: dict[str, str]
    url: str
    provider: str
    auth: Literal["ecp", "ecp_or_egov_mobile", "none"]
    evidence_for: tuple[str, ...] = ()  # taxonomy branches where it helps; empty = any
    note: dict[str, str] = Field(default_factory=dict)
    verified_on: date | None = None  # when the link was last confirmed

    @field_validator("url")
    @classmethod
    def _https(cls, v: str) -> str:
        if not v.startswith("https://"):
            raise ValueError("gov service url must be https")
        return v


class GovServices(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    services: tuple[GovService, ...]


class JurisdictionPack:
    def __init__(self, root: Path, packs_root: Path, manifest: PackManifest,
                 i18n: dict[str, dict], scenarios: dict[str, Scenario], demo_lawyers: dict | None = None,
                 coverage: Coverage | None = None, agreements: AgreementSet | None = None,
                 gov_services: GovServices | None = None):
        self.agreements = agreements
        self.gov_services = gov_services
        self.demo_lawyers = demo_lawyers or {}
        self.coverage = coverage
        self.root = root
        self.packs_root = packs_root
        self.manifest = manifest
        self.i18n = i18n
        self.scenarios = scenarios

    # ---- identity ------------------------------------------------------
    @property
    def country(self) -> str:
        return self.manifest.country

    @property
    def currency(self) -> str:
        return self.manifest.currency

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.manifest.timezone)

    # ---- i18n ----------------------------------------------------------
    def t(self, lang: str, key: str, default: str | None = None, **kwargs: Any) -> str:
        for candidate in (lang, self.manifest.default_language):
            node: Any = self.i18n.get(candidate, {})
            for part in key.split("."):
                node = node.get(part) if isinstance(node, dict) else None
            if isinstance(node, str):
                return node.format_map(_SafeDict(kwargs)) if kwargs else node
        return default if default is not None else key

    def localized(self, value: Localized, lang: str) -> str:
        return value.get(lang) or value.get(self.manifest.default_language) or next(iter(value.values()), "")

    def lang(self, lang: str | None) -> str:
        return lang if lang in self.manifest.languages else self.manifest.default_language

    # ---- calendar ------------------------------------------------------
    def add_days(self, start: date, calendar_days: int | None, business_days: int | None) -> date:
        if calendar_days is not None:
            return start + timedelta(days=calendar_days)
        assert business_days is not None
        d, left = start, business_days
        holidays = set(self.manifest.holidays)
        while left:
            d += timedelta(days=1)
            if d.weekday() < 5 and d not in holidays:
                left -= 1
        return d

    def local_now(self) -> datetime:
        return datetime.now(self.tz)


class _SafeDict(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def load_pack(root: Path, packs_root: Path) -> JurisdictionPack:
    manifest_path = root / "pack.yaml"
    try:
        manifest = PackManifest.model_validate(yaml.safe_load(manifest_path.read_text("utf-8")))
    except (ValidationError, yaml.YAMLError) as e:
        raise PackValidationError(f"{manifest_path}: {e}") from e
    if manifest.default_language not in manifest.languages:
        raise PackValidationError(f"{manifest_path}: default_language not in languages")
    for lang in manifest.languages:
        if lang not in manifest.compliance.ai_label:
            raise PackValidationError(f"{manifest_path}: compliance.ai_label missing {lang!r}")

    i18n: dict[str, dict] = {}
    for lang in manifest.languages:
        p = root / "i18n" / f"{lang}.yaml"
        if p.is_file():
            i18n[lang] = yaml.safe_load(p.read_text("utf-8")) or {}

    scenarios: dict[str, Scenario] = {}
    errors: list[str] = []
    for path in sorted((root / "scenarios").glob("*.yaml")):
        try:
            sc = load_scenario_file(path, packs_root=packs_root)
        except ScenarioValidationError as e:
            errors.append(str(e))
            continue
        if sc.jurisdiction != manifest.country:
            errors.append(f"{path}: jurisdiction {sc.jurisdiction} ≠ pack {manifest.country}")
            continue
        extra = set(sc.languages) - set(manifest.languages)
        if extra:
            errors.append(f"{path}: languages {sorted(extra)} not supported by pack")
            continue
        for a in sc.actions:
            if a.addressee and a.addressee.authority and a.addressee.authority not in manifest.authorities:
                errors.append(f"{path}: action {a.id} refers to unknown authority {a.addressee.authority!r}")
        if sc.id in scenarios:
            errors.append(f"{path}: duplicate scenario id {sc.id}")
        scenarios[sc.id] = sc
    coverage = None
    try:
        coverage = load_coverage(root, packs_root, manifest.country, manifest.languages)
    except CoverageValidationError as e:
        errors += e.errors
    if coverage is not None:
        for sc in scenarios.values():
            if sc.taxonomy and sc.taxonomy not in coverage.disputes:
                errors.append(f"scenario {sc.id}: taxonomy {sc.taxonomy!r} is not a known dispute type")
    if errors:
        raise PackValidationError("\n".join(errors))
    demo_path = root / "demo" / "lawyers.yaml"
    demo = yaml.safe_load(demo_path.read_text("utf-8")) if demo_path.is_file() else {}
    agreements = None
    agreements_path = root / "agreements.yaml"
    if agreements_path.is_file():
        try:
            agreements = AgreementSet.model_validate(yaml.safe_load(agreements_path.read_text("utf-8")))
        except (ValidationError, yaml.YAMLError) as e:
            raise PackValidationError(f"{agreements_path}: {e}") from e
    gov = None
    gov_path = root / "gov_services.yaml"
    if gov_path.is_file():
        try:
            gov = GovServices.model_validate(yaml.safe_load(gov_path.read_text("utf-8")))
        except (ValidationError, yaml.YAMLError) as e:
            raise PackValidationError(f"{gov_path}: {e}") from e
    return JurisdictionPack(root, packs_root, manifest, i18n, scenarios, demo, coverage, agreements, gov)


class PackRegistry:
    """All jurisdiction packs found under one directory."""

    def __init__(self, packs: dict[str, JurisdictionPack]):
        self.packs = packs
        self._generic: dict[str, Scenario] = {}

    @classmethod
    def load(cls, packs_root: Path) -> "PackRegistry":
        packs: dict[str, JurisdictionPack] = {}
        for sub in sorted(p for p in packs_root.iterdir() if (p / "pack.yaml").is_file()):
            pack = load_pack(sub, packs_root)
            packs[pack.country] = pack
            log.info("loaded pack %s with %d scenarios", pack.country, len(pack.scenarios))
        return cls(packs)

    def pack(self, country: str) -> JurisdictionPack:
        return self.packs[country.upper()]

    def pack_for_scenario(self, scenario_id: str) -> JurisdictionPack:
        ref = GenericRef.parse(scenario_id)
        if ref is not None:
            return self.pack(ref.country)
        for pack in self.packs.values():
            if scenario_id in pack.scenarios:
                return pack
        raise KeyError(scenario_id)

    def scenario(self, scenario_id: str) -> Scenario:
        ref = GenericRef.parse(scenario_id)
        if ref is not None:  # universal path: rebuilt from registry data, cached per id
            if scenario_id not in self._generic:
                self._generic[scenario_id] = build_generic_scenario(self.pack(ref.country), ref)
            return self._generic[scenario_id]
        return self.pack_for_scenario(scenario_id).scenarios[scenario_id]

    def published(self, country: str | None = None) -> list[Scenario]:
        """Published scenarios; test packs are only visible when asked for by country."""
        out = []
        for pack in self.packs.values():
            if country and pack.country != country.upper():
                continue
            if not country and pack.manifest.status != "live":
                continue
            out.extend(s for s in pack.scenarios.values() if s.published)
        return out
