"""Small CLI: validate packs, list lawyer TODOs, run a scheduler tick.

    python -m konsilier.cli validate [PACKS_DIR]
    python -m konsilier.cli todos [PACKS_DIR]
    python -m konsilier.cli tick
"""

from __future__ import annotations

import sys
from pathlib import Path

from .config import get_settings
from .core.packs import PackRegistry, PackValidationError


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in ("validate", "todos", "tick"):
        print(__doc__)
        return 2
    cmd = argv[0]
    if cmd == "tick":
        from .container import build_container

        print("reminders sent:", build_container(get_settings()).scheduler.tick())
        return 0
    packs_dir = Path(argv[1]) if len(argv) > 1 else get_settings().packs_dir
    try:
        registry = PackRegistry.load(packs_dir)
    except PackValidationError as e:
        print(f"INVALID:\n{e}", file=sys.stderr)
        return 1
    for pack in registry.packs.values():
        for sc in pack.scenarios.values():
            state = "DRAFT" if sc.is_draft else f"reviewed {sc.reviewed_at}"
            if cmd == "validate":
                print(f"OK  {sc.id}@{sc.version}  [{state}]  published={sc.published}")
            else:
                for todo in sc.todos():
                    print(todo)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
