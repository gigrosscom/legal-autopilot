"""Production smoke check: the whole path as a marked test user — story → documents → interview → payment window →
payment confirmed → the document — with timings. Test users stay out of the metrics and the operations centre and
never notify the team (konsilier/api/smoke.py).

    SMOKE_TOKEN=... python deploy/smoke.py [--api https://api.konsilier.com] [--story "..."]

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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="https://api.konsilier.com")
    ap.add_argument("--story", default=STORY)
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
