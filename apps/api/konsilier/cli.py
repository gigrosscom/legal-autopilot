"""Small CLI: validate packs, list lawyer TODOs, run a scheduler tick.

    python -m konsilier.cli validate [PACKS_DIR]
    python -m konsilier.cli todos [PACKS_DIR]
    python -m konsilier.cli tick
    python -m konsilier.cli backup      # pg_dump → S3 bucket (backups/…) or ./data/backups
    python -m konsilier.cli reissue-documents [--apply]   # «Проверьте данные перед подачей» out of given documents
    python -m konsilier.cli review CC [PACKS_DIR]   # refresh the generated table in packs/<cc>/REVIEW.md
    python -m konsilier.cli forums-export CC OUT.yaml  # admin drafts → YAML for a reviewed PR
    python -m konsilier.cli zann-bench [PATH] [--no-examples] [--limit N] [--out REPORT.json]  # score the system
    python -m konsilier.cli zann-export OUT.jsonl [--with-evidence]   # consented, anonymised cases for training
    python -m konsilier.cli official-crawl [CC] [--limit N] [--minutes M]  # refresh the library of official pages
    python -m konsilier.cli official-search "query" [CC] [--lang ru] [--limit N]
    python -m konsilier.cli zann-corpus [--limit N] [--minutes M] [--discover]  # Zann law corpus from adilet
    python -m konsilier.cli zann-court [--limit N] [--minutes M] [--discover]   # court practice from sud.kz
    python -m konsilier.cli zann-court-import DIR [--category C] [--court NAME]  # court acts from a lawful export
    python -m konsilier.cli zann-court-export OUT.jsonl [--source np,review] [--category labour] [--limit N]
                                                         # anonymised texts only (originals never leave the server)
"""

from __future__ import annotations

import sys
from pathlib import Path

from .config import get_settings
from .core.packs import PackRegistry, PackValidationError


def main(argv: list[str]) -> int:
    if argv and argv[0] == "backup":
        return backup()
    if argv and argv[0] == "reissue-documents":
        return reissue_documents("--apply" in argv)
    if argv and argv[0] == "official-crawl":
        return official_crawl(argv[1:])
    if argv and argv[0] == "official-search" and len(argv) > 1:
        return official_search(argv[1:])
    if argv and argv[0] == "zann-corpus":
        return zann_corpus(argv[1:])
    if argv and argv[0] == "zann-court":
        return zann_court(argv[1:])
    if argv and argv[0] == "zann-court-import" and len(argv) > 1:
        return zann_court_import(argv[1:])
    if argv and argv[0] == "zann-court-export" and len(argv) > 1:
        return zann_court_export(argv[1:])
    if argv and argv[0] == "zann-bench":
        return zann_bench(argv[1:])
    if argv and argv[0] == "zann-export" and len(argv) > 1:
        return zann_export(Path(argv[1]), "--with-evidence" in argv)
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


def reissue_documents(apply: bool) -> int:
    """Owner 02.10: «Проверьте данные перед подачей» out of every document already given (dry run without --apply)."""
    from .container import build_container
    from .core.reissue import reissue_all

    container = build_container(get_settings())
    with container.session_factory() as s:
        out = reissue_all(s, container.storage, container.engine.pdf, apply)
        if apply:
            s.commit()
    print(out)
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


def zann_bench(args: list[str]) -> int:
    import json

    from .zann import bench

    def opt(name: str) -> str | None:
        return args[args.index(name) + 1] if name in args and args.index(name) + 1 < len(args) else None
    paths = [a for i, a in enumerate(args) if not a.startswith("--") and (i == 0 or args[i - 1] not in ("--limit", "--out"))]
    path = Path(paths[0]) if paths else Path(__file__).resolve().parents[3] / "zann" / "bench"
    report = bench.run(get_settings(), bench.load(path), with_examples="--no-examples" not in args,
                       limit=int(opt("--limit")) if opt("--limit") else None)
    for r in report["results"]:
        if not r["ok"]:
            print(f"FAIL {r['id']}: expected {r['expect']}, got {r['got']}")
    print(f"model: {report['model']}")
    for key, v in report["score"].items():
        print(f"{key:<24} {v['ok']}/{v['total']}  {v['accuracy']:.0%}")
    if opt("--out"):
        Path(opt("--out")).write_text(json.dumps(report, ensure_ascii=False, indent=1), "utf-8")
    return 0


def zann_export(out: Path, with_evidence: bool) -> int:
    import json

    from .zann.export import export
    from .container import build_container

    container = build_container(get_settings())
    n = 0
    with container.session_factory() as session, out.open("w", encoding="utf-8") as f:
        for record in export(session, container.engine, with_evidence=with_evidence):
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            n += 1
    print(f"{n} cases → {out}")
    return 0


def _opt(args: list[str], name: str) -> str | None:
    return args[args.index(name) + 1] if name in args and args.index(name) + 1 < len(args) else None


def _positional(args: list[str], with_value: tuple[str, ...]) -> list[str]:
    return [a for i, a in enumerate(args) if not a.startswith("--") and (i == 0 or args[i - 1] not in with_value)]


def official_crawl(args: list[str]) -> int:
    """Refresh the library of official pages now (the nightly job does the same, time-boxed)."""
    from .container import build_container
    from .official.crawler import Crawler

    settings = get_settings()
    container = build_container(settings)
    names = [a.upper() for a in _positional(args, ("--limit", "--minutes"))]
    limit, minutes = _opt(args, "--limit"), _opt(args, "--minutes")
    for cc in names or sorted(container.official_sources):
        src = container.official_sources.get(cc)
        if src is None:
            print(f"{cc}: the pack has no sources/official.yaml", file=sys.stderr)
            return 1
        stats = Crawler(container.session_factory, src, max_pages=settings.official_crawl_max_pages).run(
            limit=int(limit) if limit else None, budget_seconds=float(minutes) * 60 if minutes else None)
        for domain, s in sorted(stats.items()):
            print(f"{cc} {domain:<24} " + " ".join(f"{k}={v}" for k, v in vars(s).items()))
    return 0


def zann_corpus(args: list[str]) -> int:
    """Collect the Zann law corpus now (the job does the same, time-boxed): --discover walks only the portal's
    index (act codes, no texts); --limit N reads at most N acts; --minutes M stops after M minutes."""
    import json
    from dataclasses import asdict

    from .container import build_container
    from .zann.corpus import build_collector, corpus_metrics

    settings = get_settings()
    container = build_container(settings)
    collector = build_collector(settings, container.session_factory, container.storage)
    limit, minutes = _opt(args, "--limit"), _opt(args, "--minutes")
    stats = collector.run(budget_seconds=float(minutes) * 60 if minutes else None,
                          limit=int(limit) if limit else None, discover_only="--discover" in args)
    print("run:", json.dumps(asdict(stats), ensure_ascii=False))
    with container.session_factory() as s:
        print("corpus:", json.dumps(corpus_metrics(s), ensure_ascii=False))
    return 1 if stats.stopped in ("robots", "unreachable") else 0


def zann_court(args: list[str]) -> int:
    """Collect court practice from sud.kz now (the job does the same, time-boxed): --discover walks only the pages
    (document links, no files); --limit N downloads at most N documents; --minutes M stops after M minutes."""
    import json
    from dataclasses import asdict

    from .container import build_container
    from .zann.court import build_collector, court_metrics

    settings = get_settings()
    container = build_container(settings)
    collector = build_collector(settings, container.session_factory, container.storage)
    limit, minutes = _opt(args, "--limit"), _opt(args, "--minutes")
    stats = collector.run(budget_seconds=float(minutes) * 60 if minutes else None,
                          limit=int(limit) if limit else None, discover_only="--discover" in args)
    print("run:", json.dumps(asdict(stats), ensure_ascii=False))
    with container.session_factory() as s:
        print("court:", json.dumps(court_metrics(s), ensure_ascii=False))
    return 1 if stats.stopped in ("robots", "unreachable") else 0


def zann_court_import(args: list[str]) -> int:
    """Court acts obtained lawfully (Smart Bridge, files saved by hand) → our storage: every .pdf/.docx/.rtf/.txt/
    .html in DIR; an optional <file>.json next to a file gives its court, category, date, number, title, url."""
    import json

    from .container import build_container
    from .zann.court import build_collector

    settings = get_settings()
    container = build_container(settings)
    collector = build_collector(settings, container.session_factory, container.storage)
    folder = Path(_positional(args, ("--category", "--court"))[0])
    n = 0
    for f in sorted(folder.iterdir()):
        if f.suffix.lower() not in (".pdf", ".docx", ".rtf", ".txt", ".html", ".htm", ".doc"):
            continue
        side = f.with_suffix(f.suffix + ".json")
        meta = json.loads(side.read_text("utf-8")) if side.exists() else {}
        if _opt(args, "--category"):
            meta.setdefault("category", _opt(args, "--category"))
        if _opt(args, "--court"):
            meta.setdefault("court", _opt(args, "--court"))
        collector.import_file(f.name, f.read_bytes(), meta)
        n += 1
    collector.write_manifest()
    print(f"imported {n} file(s)")
    return 0


def zann_court_export(args: list[str]) -> int:
    """Anonymised court-practice texts as JSON lines: the only form in which they may leave the server."""
    import json

    from .container import build_container
    from .zann.anonymize import load_rules
    from .zann.court import export_anonymised, pick_country

    settings = get_settings()
    container = build_container(settings)
    rules = load_rules(settings.packs_dir, pick_country(settings.packs_dir, settings.zann_court_country))
    out = Path(_positional(args, ("--source", "--category", "--limit"))[0])
    split = lambda v: tuple(x.strip() for x in (v or "").split(",") if x.strip())  # noqa: E731
    limit = _opt(args, "--limit")
    n = 0
    with out.open("w", encoding="utf-8") as fh:
        for rec in export_anonymised(container.session_factory, container.storage, rules,
                                     sources=split(_opt(args, "--source")), categories=split(_opt(args, "--category")),
                                     limit=int(limit) if limit else None):
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n += 1
    print(f"{n} anonymised document(s) → {out}")
    return 0


def official_search(args: list[str]) -> int:
    import time

    from .container import build_container
    from .official.search import search

    container = build_container(get_settings())
    pos = _positional(args, ("--lang", "--limit"))
    cc = pos[1].upper() if len(pos) > 1 else next(iter(sorted(container.official_sources)), "")
    with container.session_factory() as s:
        t0 = time.perf_counter()
        hits = search(s, pos[0], cc, _opt(args, "--lang"), int(_opt(args, "--limit") or 5))
        ms = (time.perf_counter() - t0) * 1000
    for h in hits:
        print(f"{h.score:6.1f}  {h.url}\n        {h.title} — {h.heading}\n        {h.snippet}\n")
    print(f"{len(hits)} hit(s) in {ms:.0f} ms")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
