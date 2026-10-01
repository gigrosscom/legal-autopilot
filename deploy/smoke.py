"""Production smoke check: the whole path as a marked test user — story → documents → interview → payment window →
payment confirmed → the document — with timings. Test users stay out of the metrics and the operations centre and
never notify the team (konsilier/api/smoke.py).

    SMOKE_TOKEN=... python deploy/smoke.py [--api https://api.konsilier.com] [--story "..."]
    SMOKE_TOKEN=... python deploy/smoke.py --chat-speed    # only the chat: first words of 10 ru/kk questions

``--chat-speed``: each question opens a case the way the site does (``defer``) and streams the chat reply; the time
to the first words is measured here, and the server's own breakdown (``diagnostics`` of the ``done`` event: the
provider that answered, library search, each model round with the models tried, each tool) is printed with it. The
breakdown is sent to test accounts only.

Needs SMOKE_TOKEN (the same value as on the server). Exit code 0 = the path works end to end.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid

STORY = ("Купил пылесос в интернет-магазине 12.09.2026 за 150 000 тенге, через неделю он сломался, "
         "продавец отказывается вернуть деньги")
RECEIPT = "ТОО Тест-Магазин\nКассовый чек от 12.09.2026\nПылесос Smoke 1\nИТОГО: 150000"
ANSWERS = {"date": "12.09.2026", "money": "150000", "phone": "+7 700 000 00 00", "email": "smoke@konsilier.com",
           "number": "1"}
TEXT = "Тестовая проверка сервиса: товар сломался, продавец не возвращает деньги"


class Api:
    def __init__(self, base: str, token: str | None = None, smoke: str | None = None):
        self.base, self.token, self.smoke = base.rstrip("/"), token, smoke

    def call(self, method: str, path: str, body: object = None, *, raw: bool = False,
             form: tuple[bytes, str] | None = None) -> object:
        headers = {}
        data = None
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if self.smoke:
            headers["X-Smoke-Token"] = self.smoke
        if form is not None:
            data, headers["Content-Type"] = form
        elif body is not None:
            data, headers["Content-Type"] = json.dumps(body).encode(), "application/json"
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=150) as r:
                payload = r.read()
        except urllib.error.HTTPError as e:
            raise SystemExit(f"FAIL {method} {path}: HTTP {e.code} {e.read()[:400]!r}") from e
        return payload if raw else json.loads(payload or b"{}")


def multipart(fields: dict[str, str], filename: str, content: bytes, ctype: str) -> tuple[bytes, str]:
    b = uuid.uuid4().hex
    parts = [f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode() for k, v in fields.items()]
    parts.append(f'--{b}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
                 f"Content-Type: {ctype}\r\n\r\n".encode() + content + b"\r\n")
    return b"".join(parts) + f"--{b}--\r\n".encode(), f"multipart/form-data; boundary={b}"


def step(name: str, t0: float) -> float:
    now = time.monotonic()
    print(f"ok  {name:<34} {now - t0:5.1f} s")
    return now


CHAT_QUESTIONS = [
    ("ru", "Вернуть деньги за бракованный товар"),
    ("ru", "Работодатель не выплатил зарплату за два месяца, что делать?"),
    ("kk", "Жұмыс беруші екі ай жалақы төлемеді, не істеймін?"),
    ("ru", "Как получить пособие при рождении ребёнка?"),
    ("kk", "Ақаулы тауар үшін ақшаны қалай қайтарамын?"),
    ("ru", "Сосед затопил квартиру, как взыскать ущерб?"),
    ("kk", "Бала туғанда қандай жәрдемақы беріледі?"),
    ("ru", "Меня уволили без предупреждения, законно ли это?"),
    ("kk", "Көршім пәтерімді су басты, шығынды қалай өндіремін?"),
    ("ru", "Банк списал деньги без моего согласия, что делать?"),
]


def _round(x: dict) -> str:
    """One model round: the provider that answered, and each provider (and model) asked with its result."""
    out = f"{x.get('provider')}: first {x.get('first_ms')} ms, round {x.get('ms')} ms, {x.get('stop')}"
    for a in x.get("attempts") or []:
        tries = ", ".join(f"{t.get('model', '')} {t.get('status')} {t.get('ms')}ms" for t in a.get("tries") or [])
        out += (f" [{a.get('provider') or a.get('model')} {a.get('result') or a.get('status')} {a.get('ms')}ms"
                + (f": {tries}" if tries else "") + "]")
    return out


def chat_speed(api: Api) -> int:
    """First words of the chat for each question, measured here, with the server's breakdown (test accounts)."""
    firsts: list[float] = []
    for lang, q in CHAT_QUESTIONS:
        cid = api.call("POST", "/v1/cases", {"text": q, "country": "KZ", "language": lang, "accept_terms": True,
                                             "defer": True})["case"]["id"]
        req = urllib.request.Request(f"{api.base}/v1/cases/{cid}/chat", method="POST",
                                     data=json.dumps({"text": q, "language": lang}).encode(),
                                     headers={"Authorization": f"Bearer {api.token}",
                                              "Content-Type": "application/json"})
        t0 = time.monotonic()
        first, last = None, {}
        with urllib.request.urlopen(req, timeout=150) as r:
            for line in r:
                text = line.decode().strip()
                if not text.startswith("data: "):
                    continue
                last = json.loads(text[6:])
                if last.get("type") == "text" and first is None and last.get("text", "").strip():
                    first = time.monotonic() - t0
        d = last.get("diagnostics") or {}
        timing = d.get("timing") or {}
        if first is not None:
            firsts.append(first)
        print(f"{'ok ' if last.get('type') == 'done' else 'ERR'} [{lang}] first words "
              f"{'—' if first is None else f'{first:.2f}'} s · total {time.monotonic() - t0:.1f} s · server first "
              f"{d.get('first_ms')} ms · by {d.get('served_by')} · library {timing.get('library_ms')} ms · setup "
              f"{timing.get('setup_ms')} ms · queue {timing.get('queue_ms')} ms · prompt {timing.get('prompt_chars')} "
              f"chars · {q[:40]}")
        for x in timing.get("rounds", []):
            print(f"      round {_round(x)}")
        for tool in timing.get("tools", []):
            print(f"      tool {tool}")
        if last.get("type") != "done":
            print(f"      {last}")
    if not firsts:
        raise SystemExit("FAIL no chat reply started")
    firsts.sort()
    p90 = firsts[min(len(firsts) - 1, round(0.9 * (len(firsts) - 1)))]
    print(f"first words: median {firsts[len(firsts) // 2]:.2f} s · p90 {p90:.2f} s · max {firsts[-1]:.2f} s · "
          f"n={len(firsts)} of {len(CHAT_QUESTIONS)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="https://api.konsilier.com")
    ap.add_argument("--story", default=STORY)
    ap.add_argument("--chat-speed", action="store_true", help="only the chat: first words of 10 ru/kk questions")
    args = ap.parse_args()
    smoke_token = os.environ.get("SMOKE_TOKEN")
    if not smoke_token:
        raise SystemExit("SMOKE_TOKEN is not set")
    t = time.monotonic()
    start = t
    boot = Api(args.api, smoke=smoke_token)
    token = boot.call("POST", "/v1/smoke/user")["token"]
    api = Api(args.api, token=token)
    t = step("test user", t)
    if args.chat_speed:
        return chat_speed(api)

    created = api.call("POST", "/v1/cases", {"text": args.story, "country": "KZ"})
    case = created["case"]
    cid = case["id"]
    if not case.get("scenario") and (created.get("reply") or {}).get("options"):
        case = api.call("POST", f"/v1/cases/{cid}/forum", {"forum_id": created["reply"]["options"][0]["id"]})["case"]
    print(f"    case {cid} · {(case.get('scenario') or {}).get('id')} · first question: "
          f"{(case.get('question') or {}).get('field')}")
    t = step("case from the story", t)

    up = api.call("POST", f"/v1/cases/{cid}/evidence",
                  form=multipart({"kind": "other"}, "receipt.txt", RECEIPT.encode(), "text/plain"))
    print(f"    read from the receipt: {up['evidence']['extracted_facts']}")
    case = up["case"]
    t = step("document read", t)

    uploaded = True
    for _ in range(40):
        q = case.get("question")
        if not q:
            break
        if q["type"] == "evidence":
            text = "готово" if uploaded and q.get("uploaded") else "пропустить"
            uploaded = False
        elif q.get("optional"):
            text = "пропустить"
        else:
            text = ANSWERS.get(q["type"], TEXT)
            if q["type"] == "text" and q.get("pattern") and "12" in q["pattern"]:
                text = "123456789012"
        out = api.call("POST", f"/v1/cases/{cid}/messages", {"text": text})
        if out["reply"].get("error") and text != "пропустить":
            out = api.call("POST", f"/v1/cases/{cid}/messages", {"text": "пропустить"})
        case = out["case"]
    if case["status"] != "qualified":
        raise SystemExit(f"FAIL interview did not finish: status {case['status']}, question {case.get('question')}")
    t = step("interview done", t)

    out = api.call("POST", f"/v1/cases/{cid}/actions/next")
    if out.get("action_id"):
        print("    the document was already paid for (free or subscription)")
    else:
        pay = api.call("POST", f"/v1/cases/{cid}/payment", {"purpose": "document"})["case"]["payment"]
        if not pay.get("code"):
            raise SystemExit(f"FAIL no payment code: {pay}")
        print(f"    bill {pay['code']}: {pay['amount']} {pay['currency']}")
        api.call("POST", f"/v1/cases/{cid}/payment/claim")
        t = step("payment window, «Оплатить»", t)
        boot.call("POST", f"/v1/smoke/cases/{cid}/payment/confirm")
        t0 = time.monotonic()
        for _ in range(60):
            case = api.call("GET", f"/v1/cases/{cid}")
            if case["actions"]:
                break
            time.sleep(0.5)
        else:
            raise SystemExit("FAIL no document 30 s after the payment was confirmed")
        print(f"    document {time.monotonic() - t0:.1f} s after the confirmation")
        t = step("payment confirmed → document", t)
        case = api.call("GET", f"/v1/cases/{cid}")

    action = case["actions"][0]
    if action.get("approval_status") == "pending":
        # the path works; this case waits for the lawyer's check (low classification confidence or a court document)
        print(f"WARN the document waits for a lawyer's check · needs_review={case.get('needs_review')} · "
              f"confidence={case.get('qualification_confidence')} · scenario={(case.get('scenario') or {}).get('id')}")
        print(f"PASS with a lawyer check · whole path {time.monotonic() - start:.1f} s · case {cid}")
        return 0
    if not action.get("downloadable"):
        raise SystemExit(f"FAIL the document is not downloadable: {action.get('status')} {action.get('approval_status')}")
    docx = api.call("GET", f"/v1/cases/{cid}/actions/{action['id']}/document?format=docx", raw=True)
    if len(docx) < 2000:
        raise SystemExit("FAIL the document file is empty")
    t = step(f"document downloaded ({len(docx) // 1024} KB)", t)
    print(f"PASS whole path {time.monotonic() - start:.1f} s · case {cid}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
