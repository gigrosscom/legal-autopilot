"""Load and validate scenario YAML with human-readable errors."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from .schema import Scenario


class ScenarioValidationError(Exception):
    """Raised when a scenario file is not valid. ``errors`` is a list of readable lines."""

    def __init__(self, source: str, errors: list[str]):
        self.source = source
        self.errors = errors
        lines = "\n".join(f"  - {e}" for e in errors)
        super().__init__(f"Invalid scenario {source}:\n{lines}")


def _loc(loc: tuple) -> str:
    parts: list[str] = []
    for p in loc:
        if isinstance(p, int):
            parts.append(f"[{p}]")
        else:
            parts.append(("." if parts else "") + str(p))
    return "".join(parts) or "<root>"


def load_scenario_text(text: str, source: str = "<string>", packs_root: Path | None = None) -> Scenario:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        where = f"line {mark.line + 1}, column {mark.column + 1}: " if mark else ""
        problem = getattr(e, "problem", None) or str(e)
        raise ScenarioValidationError(source, [f"YAML syntax error at {where}{problem}"]) from e
    if not isinstance(data, dict):
        raise ScenarioValidationError(source, ["top level must be a mapping (key: value)"])
    try:
        scenario = Scenario.model_validate(data)
    except ValidationError as e:
        errors = []
        for err in e.errors():
            msg = err["msg"].removeprefix("Value error, ")
            errors.append(f"{_loc(err['loc'])}: {msg}")
        raise ScenarioValidationError(source, errors) from e
    if packs_root is not None:
        missing = [
            f"actions.{a.id}.template: file not found: {a.template}"
            for a in scenario.actions
            if a.template and not (packs_root / a.template).is_file()
        ]
        if missing:
            raise ScenarioValidationError(source, missing)
    return scenario


def load_scenario_file(path: Path, packs_root: Path | None = None) -> Scenario:
    return load_scenario_text(path.read_text(encoding="utf-8"), source=str(path), packs_root=packs_root)
