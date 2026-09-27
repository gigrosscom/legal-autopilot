"""Small CLI: validate packs, list lawyer TODOs, run a scheduler tick.

    python -m konsilier.cli validate [PACKS_DIR]
    python -m konsilier.cli todos [PACKS_DIR]
    python -m konsilier.cli tick
    python -m konsilier.cli backup      # pg_dump → S3 bucket (backups/…) or ./data/backups
    python -m konsilier.cli review CC [PACKS_DIR]   # refresh the generated table in packs/<cc>/REVIEW.md
    python -m konsilier.cli forums-export CC OUT.yaml  # admin drafts → YAML for a reviewed PR
"""

from __future__ import annotations

import sys
from pathlib import Path

from .config import get_settings
from .core.packs import PackRegistry, PackValidationError


def main(argv: list[str]) -> int:
    if argv and argv[0] == "backup":
        return backup()
    if argv and argv[0] == "forums-export" and len(argv) > 2:
        return forums_export(argv[1], Path(argv[2]))
    if argv and argv[0] == "review" and len(argv) > 1:
        return review(argv[1], Path(argv[2]) if len(argv) > 2 else get_settings().packs_dir)
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


def backup() -> int:
    """Dump the database with pg_dump and store it in the configured storage (S3 or local)."""
    import datetime
    import gzip
    import subprocess

    from .core.adapters.storage import build_storage

    settings = get_settings()
    url = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
    if not url.startswith("postgresql://"):
        print("backup supports PostgreSQL only", file=sys.stderr)
        return 1
    dump = subprocess.run(["pg_dump", "--no-owner", "--format=plain", url], check=True, capture_output=True).stdout
    key = f"backups/{datetime.datetime.now(datetime.timezone.utc):%Y-%m-%d_%H%M}.sql.gz"
    build_storage(settings).put(key, gzip.compress(dump), "application/gzip")
    print("backup stored:", key, f"{len(dump) // 1024} KiB")
    return 0


def forums_export(country: str, out: Path) -> int:
    """Write pending admin drafts as a forums YAML file to be reviewed and merged by PR."""
    import yaml
    from sqlalchemy import select

    from .container import build_container
    from .core.models import ForumDraft

    container = build_container(get_settings())
    with container.session_factory() as s:
        drafts = list(s.scalars(select(ForumDraft).where(ForumDraft.country == country.upper(),
                                                         ForumDraft.status == "draft").order_by(ForumDraft.id)))
        latest: dict[str, dict] = {}
        for d in drafts:
            latest[d.forum_id] = d.data  # the newest draft per forum wins
        header = (f"# Admin drafts exported {len(latest)} forum record(s) for {country.upper()}.\n"
                  "# Review with a lawyer, then merge into packs/<cc>/forums/ by pull request.\n")
        out.write_text(header + yaml.safe_dump({"forums": list(latest.values())}, allow_unicode=True,
                                               sort_keys=False), "utf-8")
        for d in drafts:
            d.status = "exported"
        s.commit()
    print(f"{out}: {len(latest)} forum(s)")
    return 0


REVIEW_BEGIN = "<!-- BEGIN generated: coverage review -->"
REVIEW_END = "<!-- END generated: coverage review -->"


def review_table(pack) -> str:
    rows = pack.coverage.review_rows() if pack.coverage else []
    lines = [REVIEW_BEGIN,
             "## Реестр универсального пути: статус проверки",
             "",
             "Генерируется командой `python -m konsilier.cli review <cc>`. Не редактировать вручную.",
             "",
             "| Вид | Запись | Статус | Кем подписано |",
             "|---|---|---|---|"]
    lines += [f"| {kind} | `{rid}` | {status} | {who} |" for kind, rid, status, who in rows]
    lines.append(REVIEW_END)
    return "\n".join(lines)


def review(country: str, packs_dir: Path) -> int:
    """Refresh the generated review table in REVIEW.md, keeping the lawyer's own notes."""
    registry = PackRegistry.load(packs_dir)
    pack = registry.pack(country)
    path = pack.root / "REVIEW.md"
    text = path.read_text("utf-8") if path.is_file() else ""
    table = review_table(pack)
    if REVIEW_BEGIN in text and REVIEW_END in text:
        head, rest = text.split(REVIEW_BEGIN, 1)
        text = head + table + rest.split(REVIEW_END, 1)[1]
    else:
        text = text.rstrip() + "\n\n" + table + "\n"
    path.write_text(text, "utf-8")
    todo = sum(1 for r in (pack.coverage.review_rows() if pack.coverage else []) if r[2] == "TODO")
    print(f"{path}: {todo} TODO")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
