"""Owner 02.10 «Какой юрист?»: no pilot lawyer is assigned, so no text a client sees may promise that «a lawyer will
confirm» a term, a body or a channel. Pack data (comments aside) and the web dictionaries stay free of it."""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PHRASES = re.compile(r"(?i)уточнит юрист|юрист уточнит|уточняется юристом|заңгер нақтылайды|lawyer will confirm|"
                     r"avukat netleştir|سيحدد المحامي|سيتحقق المحامي|سيحدده المحامي")


def _client_lines(path: Path):
    stop_words = False  # routing.yaml document_markers: the words the document check stops, never shown to a client
    for n, line in enumerate(path.read_text("utf-8").splitlines(), 1):
        if line and not line[0].isspace():
            stop_words = line.startswith("document_markers:")
        if stop_words:
            continue
        code = line.split("#", 1)[0] if path.suffix == ".yaml" else line.split("//", 1)[0]
        if PHRASES.search(code):
            yield f"{path.relative_to(REPO)}:{n}"


def test_no_lawyer_will_confirm_in_client_texts():
    files = [p for p in (REPO / "packs" / "kz").rglob("*.yaml")] + list((REPO / "apps/web/lib/dict").glob("*.ts"))
    hits = [hit for p in files for hit in _client_lines(p)]
    assert hits == [], hits
