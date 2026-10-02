"""QA gate for the chat (owner 02.10: no chat change goes to production without the 30 QA cases).

Runs the 30 QA cases of 02.10 (bare-10, chats-10, dialog-10; tests/data/qa30_2026-10-02.yaml) on the REAL chat model
with the production prompt, country rules and portal tools, and checks each case against the owner's rules:

  1. first reply: only a question (no «Что делать», no [[MORE]]) — R-32 / FACTS_FIRST; a case whose first message
     already holds the parties, the subject, the date and the sum may get the solution at once (counted apart);
  2. the documents are asked in the first reply — by the model or by the server's sentence (needs_documents_line);
  3. after the facts: the solution — «Что делать:» and at most 5 lines before «Подробнее», no question at the end;
  4. terms of days and article numbers: every one left in the reply is checked (keep_checked); the ones the server
     had to take out are listed — each is a model error the gate shows for the legal review.

    cd apps/api && GEMINI_API_KEY=… python3 scripts/qa_gate.py            # all 30, report to stdout
    QA_ONLY=B5,B8 python3 scripts/qa_gate.py                              # some cases
    QA_REPORT=../../qa-gate.md python3 scripts/qa_gate.py                  # the markdown report to a file

Exit code 1 when a threshold is missed (first reply a question ≥ 27/30, documents asked 30/30, solution shape 30/30).
The legal content of each solution is not judged by the script: the report holds the replies for ZANN's review.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from konsilier.api.chat import needs_documents_line  # noqa: E402
from konsilier.chat import ChatAgent  # noqa: E402
from konsilier.config import Settings  # noqa: E402
from konsilier.core.packs import PackRegistry  # noqa: E402
from konsilier.gemini import GeminiClient  # noqa: E402
from konsilier.lawagent.sources import Adilet  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
CASES = yaml.safe_load((Path(__file__).resolve().parents[1] / "tests/data/qa30_2026-10-02.yaml").read_text("utf-8"))
MORE = re.compile(r"\[\[\s*MORE\s*\]\]")


def solution_shape(text: str) -> tuple[bool, int, bool]:
    short = MORE.split(text)[0]
    lines = [ln for ln in short.strip().splitlines() if ln.strip()]
    ends_q = text.rstrip().endswith("?")
    return bool(MORE.search(text)) or "Что делать" in text, len(lines), ends_q


def main() -> int:
    settings = Settings()
    key = os.environ.get("GEMINI_API_KEY") or settings.gemini_api_key
    if not key:
        print("GEMINI_API_KEY is not set")
        return 2
    pack = PackRegistry.load(ROOT / "packs").pack("KZ")
    portal = [s for s in pack.manifest.legal_sources if "adilet.zan.kz" in str(s.url)]
    key_acts = [{"code": a.code, "title": pack.localized(a.title, "ru")} for s in portal for a in s.key_acts]
    fallback = tuple(m.strip() for m in settings.gemini_fallback_models.split(",") if m.strip())
    agent = ChatAgent(GeminiClient(key, fallback_models=fallback), settings.gemini_model, Adilet(), web_search=False,
                      max_tokens=settings.chat_max_tokens)
    only = {x.strip() for x in os.environ.get("QA_ONLY", "").split(",") if x.strip()}

    taken: list[str] = []

    class Taken(logging.Handler):  # what the server cut from a reply (chat=unchecked_removed), per case
        def emit(self, record: logging.LogRecord) -> None:
            msg = record.getMessage()
            if msg.startswith("chat=unchecked_removed "):
                taken.extend(json.loads(msg.split(" ", 1)[1]) if msg.rstrip().endswith("]") else [msg])

    logging.getLogger("konsilier.chat").addHandler(Taken())

    def ask(history: list[dict[str, str]]) -> str:
        result = None
        for ev in agent.stream(history, context={"pack": pack, "lang": "ru", "case": {}, "key_acts": key_acts},
                               language="the language with ISO 639-1 code 'ru'", country="Kazakhstan",
                               use_portal=bool(portal)):
            if ev["type"] == "done":
                result = ev["result"]
        return result.text if result else ""

    rows = []
    for c in CASES:
        if only and c["id"] not in only:
            continue
        taken.clear()
        first = ask([{"role": "user", "text": c["first"]}])
        is_solution, _, _ = solution_shape(first)
        docs = "model" if re.search(r"пришлите|прикрепите|загрузите|отправьте\s+(?:фото|скан|копи)", first, re.I) \
            else "server" if needs_documents_line(first, asked_before=False, offer=False, files=False,
                                                    told=c["first"]) else ""
        history = [{"role": "user", "text": c["first"]}, {"role": "assistant", "text": first}]
        answer, extra = first, 0
        while not solution_shape(answer)[0] and extra < 3:
            history.append({"role": "user", "text": c["facts"] if extra == 0 else "Других данных нет, всё что знаю — выше."})
            answer = ask(history)
            history.append({"role": "assistant", "text": answer})
            extra += 1
        _, lines, ends_q = solution_shape(answer)
        removed = list(taken)
        rows.append({"id": c["id"], "first_is_question": not is_solution, "docs": docs or "NO",
                     "turns_to_solution": extra, "solution_lines": lines, "ends_with_question": ends_q,
                     "solved": solution_shape(answer)[0], "taken_out": removed, "first": first, "solution": answer})
        print(f"{c['id']:4} first={'Q' if not is_solution else 'SOL'} docs={docs or 'NO':6} "
              f"turns={extra} lines={lines} ends_q={ends_q} taken_out={len(removed)}", flush=True)

    n = len(rows)
    q = sum(r["first_is_question"] for r in rows)
    d = sum(r["docs"] != "NO" for r in rows)
    shape = sum(r["solved"] and r["solution_lines"] <= 6 and not r["ends_with_question"] for r in rows)
    summary = (f"first reply a question {q}/{n}; documents asked {d}/{n}; solution shape {shape}/{n}; "
               f"terms taken out by the server {sum(len(r['taken_out']) for r in rows)}")
    print(summary)
    report = os.environ.get("QA_REPORT")
    if report:
        out = ["# QA-гейт чата — 30 кейсов", "", summary, "", "| # | 1-й ответ | Документы | Ходов до решения | "
               "Строк | Вопрос в конце | Вырезано сервером |", "|---|---|---|---|---|---|---|"]
        out += [f"| {r['id']} | {'вопрос' if r['first_is_question'] else 'решение'} | {r['docs']} | "
                f"{r['turns_to_solution']} | {r['solution_lines']} | {'да' if r['ends_with_question'] else 'нет'} | "
                f"{'; '.join(r['taken_out']) or '—'} |" for r in rows]
        out += ["", "## Ответы (для юридической сверки ZANN)"]
        for r in rows:
            out += ["", f"### {r['id']}", "", "**1-й ответ:**", "", r["first"], "", "**Решение:**", "", r["solution"]]
        Path(report).write_text("\n".join(out) + "\n", "utf-8")
        Path(report).with_suffix(".json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), "utf-8")
    ok = n == 0 or (q >= n * 0.9 and d == n and shape == n)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
