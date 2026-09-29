"""The sources of the official library, as country-pack data: ``packs/<cc>/sources/official.yaml``.

Which domains may be crawled (the allow-list), what to follow on each of them, and the seed pages by topic. The
core knows no domain names: everything site-specific (paths worth following, query parameters that select the
language, links hidden in page data) is written here, next to the other data of the country.
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlencode, urljoin, urlsplit, urlunsplit

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

Localized = dict[str, str]

SOURCES_FILE = Path("sources") / "official.yaml"


class SourcesValidationError(Exception):
    pass


class LinkPattern(BaseModel):
    """A link written in page data rather than in an <a href>: ``match`` finds it in the raw HTML, ``url`` builds
    the page address from its groups ({1}, {2}…)."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    match: str
    url: str

    @field_validator("match")
    @classmethod
    def _regex(cls, v: str) -> str:
        re.compile(v)
        return v


class Domain(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    domain: str = Field(pattern=r"^[a-z0-9.-]+\.[a-z]{2,}$")  # exact host; subdomains need their own entry
    name: Localized = Field(default_factory=dict)  # how the chat names the portal
    about: Localized = Field(default_factory=dict)  # what people find there: the chat points to it when unsure
    lang: str = "ru"  # language of pages whose address does not say it
    include: tuple[str, ...] = ()  # path(+query) regexes of pages worth following; empty = the whole site
    exclude: tuple[str, ...] = ()
    keep_query: tuple[str, ...] = ()  # query parameters that change the page (e.g. its language); others are dropped
    default_query: dict[str, str] = Field(default_factory=dict)  # added when a followed link lacks them
    link_patterns: tuple[LinkPattern, ...] = ()
    hubs: tuple[str, ...] = ()  # path(+query) regexes of pages read only for their links, never searched
    drop: tuple[str, ...] = ()  # regexes of the site's boilerplate lines (text blocks) left out of the text
    max_pages: int | None = None  # overrides the file's max_pages_per_domain

    @field_validator("include", "exclude", "hubs", "drop")
    @classmethod
    def _regexes(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        for p in v:
            re.compile(p)
        return v


class OfficialSources(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    country: str = Field(pattern=r"^[A-Z]{2}$")
    max_pages_per_domain: int = 400
    max_depth: int = 2  # link steps followed from a seed page
    domains: tuple[Domain, ...]
    seeds: dict[str, tuple[str, ...]]  # topic → seed page URLs

    @model_validator(mode="after")
    def _seeds_on_allowed_domains(self) -> "OfficialSources":
        hosts = {d.domain for d in self.domains}
        if len(hosts) != len(self.domains):
            raise ValueError("domains must be unique")
        for topic, urls in self.seeds.items():
            for u in urls:
                host = urlsplit(u).hostname or ""
                if host not in hosts:
                    raise ValueError(f"seed {u} ({topic}) is not on an allowed domain")
        return self

    # ---------------------------------------------------------------- helpers used by the crawler
    def domain_of(self, url: str) -> Domain | None:
        """The allow-list entry of a URL, or None when the URL is not on an allowed domain (or not http(s))."""
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https"):
            return None
        return next((d for d in self.domains if d.domain == (parts.hostname or "").lower()), None)

    def cap(self, d: Domain) -> int:
        return d.max_pages or self.max_pages_per_domain

    def normalize(self, url: str, base: str | None = None) -> str | None:
        """Absolute https URL without fragment and with only the query parameters that matter; None when the URL
        is off the allow-list."""
        url = urljoin(base, url.strip()) if base else url.strip()
        d = self.domain_of(url)
        if d is None:
            return None
        p = urlsplit(url)
        query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=False) if k in d.keep_query]
        have = {k for k, _ in query}
        query += [(k, v) for k, v in d.default_query.items() if k not in have]
        path = re.sub(r"/{2,}", "/", unquote(p.path) or "/")  # one spelling for %D0%… and Cyrillic paths
        return urlunsplit(("https", d.domain, path, urlencode(sorted(query)), ""))

    @staticmethod
    def _target(url: str) -> str:
        p = urlsplit(url)
        return p.path + (f"?{p.query}" if p.query else "")

    def follow(self, url: str) -> bool:
        """Whether a found link is worth fetching (include / exclude of its domain)."""
        d = self.domain_of(url)
        if d is None:
            return False
        target = self._target(url)
        if d.include and not any(re.search(r, target) for r in d.include):
            return False
        return not any(re.search(r, target) for r in d.exclude)

    def is_hub(self, url: str) -> bool:
        d = self.domain_of(url)
        return d is not None and any(re.search(r, self._target(url)) for r in d.hubs)

    def seed_list(self) -> list[tuple[str, str]]:
        """(topic, normalized url) of every seed."""
        out: list[tuple[str, str]] = []
        for topic, urls in self.seeds.items():
            for u in urls:
                n = self.normalize(u)
                if n:
                    out.append((topic, n))
        return out


def load_sources(pack_root: Path) -> OfficialSources | None:
    path = pack_root / SOURCES_FILE
    if not path.is_file():
        return None
    try:
        return OfficialSources.model_validate(yaml.safe_load(path.read_text("utf-8")))
    except (ValidationError, yaml.YAMLError) as e:
        raise SourcesValidationError(f"{path}: {e}") from e
