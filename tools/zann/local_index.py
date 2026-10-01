#!/usr/bin/env python3
"""Local Zann article index for the bench: the texts collect_laws.py saved (data/zann/corpus/<code>.<lang>.txt and
data/zann/manifest.jsonl) loaded into a local database (SQLite by default) and split into articles with the same
Indexer the server runs (konsilier/zann/index.py). No network.

    python tools/zann/collect_laws.py --from-packs            # first: the texts (polite, 3 s between requests)
    python tools/zann/local_index.py                          # → data/zann/index.sqlite
    python tools/zann/bench_run.py --index-db sqlite:///data/zann/index.sqlite …

data/zann/ is git-ignored: neither the texts nor the index are committed.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "apps" / "api"))

from konsilier.core.adapters.storage import LocalStorage  # noqa: E402
from konsilier.core.db import make_engine, make_session_factory  # noqa: E402
from konsilier.core.models import Base, ZannAct, ZannArticle, ZannFile, ZannIndexed  # noqa: E402
from konsilier.zann.corpus import doc_url  # noqa: E402
from konsilier.zann.index import Indexer, index_metrics  # noqa: E402

KEY = "zann/corpus/{code}.{lang}.txt.gz"


def act_type(code: str, title: str) -> str:
    """The portal's «вид акта» guessed from the code and title: codes (K…) and laws (Z…) rank above by-laws."""
    t = title.lower()
    if code.startswith("K") and ("кодекс" in t or "кодекс" in t.replace("i", "і")):
        return "КОД"
    if code.startswith("Z"):
        return "ЗАК"
    return ""


def build(corpus: Path, manifest: Path, db_url: str, storage_dir: Path) -> dict:
    rows = [json.loads(x) for x in manifest.read_text("utf-8").splitlines() if x.strip()]
    engine = make_engine(db_url)
    Base.metadata.create_all(engine, tables=[t.__table__ for t in (ZannAct, ZannFile, ZannArticle, ZannIndexed)])
    sf = make_session_factory(engine)
    storage = LocalStorage(storage_dir)
    now = datetime.now(timezone.utc)
    with sf() as s:
        for r in rows:
            path = corpus / f"{r['code']}.{r['lang']}.txt"
            if not path.exists():
                continue
            text = path.read_text("utf-8")
            data = gzip.compress(text.encode("utf-8"))
            key = storage.put(KEY.format(code=r["code"], lang=r["lang"]), data)
            sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
            f = s.get(ZannFile, (r["code"], r["lang"])) or ZannFile(code=r["code"], lang=r["lang"])
            f.key, f.url, f.title, f.sha256 = key, doc_url(r["code"], r["lang"]), r.get("title") or "", sha
            f.chars, f.bytes, f.fetched_at, f.changed_at = len(text), len(data), now, now
            s.merge(f)
            if r["lang"] == "ru" or s.get(ZannAct, r["code"]) is None:
                a = s.get(ZannAct, r["code"]) or ZannAct(code=r["code"])
                a.title, a.act_type, a.status, a.state = r.get("title") or "", act_type(r["code"], r.get("title") or ""), "upd", "done"
                s.merge(a)
        s.commit()
    stats = Indexer(sf, storage).run()
    with sf() as s:
        return {"run": vars(stats), "index": index_metrics(s)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--corpus", type=Path, default=REPO / "data" / "zann" / "corpus")
    ap.add_argument("--manifest", type=Path, default=REPO / "data" / "zann" / "manifest.jsonl")
    ap.add_argument("--db", default=f"sqlite:///{REPO / 'data' / 'zann' / 'index.sqlite'}")
    ap.add_argument("--storage", type=Path, default=REPO / "data" / "zann" / "storage")
    a = ap.parse_args(argv)
    print(json.dumps(build(a.corpus, a.manifest, a.db, a.storage), ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
