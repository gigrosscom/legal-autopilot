"""The library of official pages: pages of the state portals a country pack allows, fetched at night and searched
instantly by the consultation chat (docs/official-library.md).

- config.py — the pack's sources file (allowed domains, what to follow, seed pages by topic)
- crawler.py — polite fetch, main-text extraction, storage of changed pages as chunks
- search.py — ``search(session, query, country, lang, limit)`` and ``OfficialLibrary`` used by the chat
- job.py — the nightly scheduler job
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import OfficialSources, SourcesValidationError, load_sources


def load_all(packs: Any) -> dict[str, OfficialSources]:
    """country → sources, for every pack that has a sources file."""
    out: dict[str, OfficialSources] = {}
    for pack in packs.packs.values():
        src = load_sources(Path(pack.root))
        if src is not None:
            if src.country != pack.country:
                raise SourcesValidationError(f"{pack.root}: sources country {src.country} ≠ pack {pack.country}")
            out[pack.country] = src
    return out
