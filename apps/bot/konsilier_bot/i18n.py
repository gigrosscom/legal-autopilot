from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

LOCALES = Path(__file__).parent / "locales"
DEFAULT = "ru"


@lru_cache
def _load(lang: str) -> dict[str, Any]:
    path = LOCALES / f"{lang}.yaml"
    return yaml.safe_load(path.read_text("utf-8")) if path.exists() else {}


def t(key: str, lang: str = DEFAULT, **kwargs: Any) -> str:
    for candidate in (lang, DEFAULT):
        node: Any = _load(candidate)
        for part in key.split("."):
            node = node.get(part) if isinstance(node, dict) else None
        if isinstance(node, str):
            return node.format(**kwargs) if kwargs else node
    return key
