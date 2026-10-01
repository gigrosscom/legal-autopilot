"""Production smoke check: the whole path as a marked test user — story → documents → interview → payment window →
payment confirmed → the document — with timings. Test users stay out of the metrics and the operations centre and
never notify the team (konsilier/api/smoke.py).

    SMOKE_TOKEN=... python deploy/smoke.py [--api https://api.konsilier.com] [--story "..."]
    SMOKE_TOKEN=... python deploy/smoke.py --chat-speed    # only the chat: first words of 10 ru/kk questions
    SMOKE_TOKEN=... python deploy/smoke.py --path3         # question → document for 3 cases: time and taps
    SMOKE_TOKEN=... python deploy/smoke.py --chat-check 20 [--same "..."]  # whole answers: none cut, question last

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


PATH3 = [  # owner 01.10, KPI: from the question to the document in 3 minutes — three typical cases
    ("refund", "Купил пылесос в интернет-магазине 12.09.2026 за 150 000 тенге, через неделю он сломался, продавец "
               "ТОО «Тест-Магазин» отказывается вернуть деньги. Составьте претензию.", RECEIPT),
    ("salary", "Работодатель ТОО «Тест-Работодатель» не выплатил мне зарплату за август и сентябрь 2026, всего "
               "600 000 тенге. Хочу получить деньги. Составьте документ.", None),
    ("gov", "Акимат района не ответил на моё обращение о ремонте дороги, поданное 01.08.2026, прошло больше двух "
            "месяцев. Хочу пожаловаться. Составьте жалобу.", None),
]


APPLICANT = {"applicant_name": "Тестов Тест Тестович", "applicant_iin": "900101300123",
             "applicant_address": "г. Алматы, ул. Абая, 1", "applicant_phone": "+7 700 000 00 00"}


def path3(api: Api, boot: Api) -> int:
    """The client's path as the site runs it after «3 клика» (PR #121), timed from the first message to the document
    file, with the taps it takes: send (with the files) · «Составить документ» · «Подготовить документ» (the bill) ·
    «Я оплатил(а)» · open the document. The payment is confirmed by the smoke hook (the desk / Kaspi in real life)."""
    failed = 0
    for name, story, receipt in PATH3:
        t0, taps = time.monotonic(), 0
        try:
            case = api.call("POST", "/v1/cases", {"text": story, "country": "KZ"})["case"]
            taps += 1  # send
            cid = case["id"]
            if receipt:
                case = api.call("POST", f"/v1/cases/{cid}/evidence",
                                form=multipart({"kind": "other"}, "receipt.txt", receipt.encode(), "text/plain"))["case"]
            answered = 0
            while case["status"] == "intake" and case.get("question") and answered < 10:  # questions still asked
                q = case["question"]
                text = "пропустить" if q["type"] == "evidence" or q.get("optional") else ANSWERS.get(q["type"], TEXT)
                case = api.call("POST", f"/v1/cases/{cid}/messages", {"text": text})["case"]
                answered += 1
                taps += 1
            taps += 1  # «Составить документ» → the draft
            blanks, own = 0, {}
            try:
                fields = api.call("GET", f"/v1/cases/{cid}/draft").get("blanks", [])
                blanks = len(fields)
                own = {f["field"]: APPLICANT[f["field"]] for f in fields if f["field"] in APPLICANT}
            except SystemExit:
                pass
            if own:  # the applicant's own data, one screen right before paying (PM 01.10)
                api.call("POST", f"/v1/cases/{cid}/facts", {"values": own})
                taps += 1
            if case["status"] != "qualified":
                raise SystemExit(f"status {case['status']}")
            pay = api.call("POST", f"/v1/cases/{cid}/payment", {"purpose": "document"})["case"]["payment"]
            taps += 1  # «Подготовить документ» = the bill
            if pay.get("status") != "paid":
                api.call("POST", f"/v1/cases/{cid}/payment/claim")
                taps += 1  # «Я оплатил(а)»
                boot.call("POST", f"/v1/smoke/cases/{cid}/payment/confirm")
            for _ in range(240):
                case = api.call("GET", f"/v1/cases/{cid}")
                if case["actions"]:
                    break
                time.sleep(0.5)
            else:
                raise SystemExit("no document 120 s after payment")
            a = case["actions"][0]
            taps += 1  # open / download
            state = "review" if a.get("approval_status") == "pending" else "ready" if a.get("downloadable") else a.get("status")
            print(f"path3 {name}={time.monotonic() - t0:.0f}s taps={taps} questions={answered} blanks={blanks} "
                  f"doc={state} scenario={(case.get('scenario') or {}).get('id')}")
        except SystemExit as e:
            failed += 1
            print(f"path3 {name}=FAIL after {time.monotonic() - t0:.0f}s: {str(e)[:160]}")
    return 1 if failed else 0


CHECK_QUESTIONS = CHAT_QUESTIONS + [
    ("ru", "Магазин не меняет телефон по гарантии, что делать?"),
    ("kk", "Дүкен кепілдік бойынша телефонды ауыстырмайды, не істеймін?"),
    ("ru", "Как подать на алименты?"),
    ("kk", "Алимент өндіру үшін қайда жүгінемін?"),
    ("ru", "Не вернули залог за съёмную квартиру"),
    ("kk", "Жалдаған пәтердің кепіл ақшасын қайтармады"),
    ("ru", "Оштрафовали за парковку незаконно, как обжаловать?"),
    ("kk", "Жұмыстан заңсыз шығарды, не істеуге болады?"),
    ("ru", "Застройщик задерживает сдачу квартиры уже полгода"),
    ("ru", "Купил подписку, отменил, а деньги всё равно списывают"),
]
_END = (".", "!", "?", "…", ")", "»", "*", ":")


def _ask(api: Api, lang: str, q: str) -> tuple[float | None, float, dict, str]:
    """One chat reply the way the site asks it: (first words s, total s, the done/error event, the streamed text)."""
    cid = api.call("POST", "/v1/cases", {"text": q, "country": "KZ", "language": lang, "accept_terms": True,
                                         "defer": True})["case"]["id"]
    req = urllib.request.Request(f"{api.base}/v1/cases/{cid}/chat", method="POST",
                                 data=json.dumps({"text": q, "language": lang}).encode(),
                                 headers={"Authorization": f"Bearer {api.token}", "Content-Type": "application/json"})
    t0 = time.monotonic()
    first, last, streamed = None, {}, ""
    with urllib.request.urlopen(req, timeout=150) as r:
        for line in r:
            text = line.decode().strip()
            if not text.startswith("data: "):
                continue
            last = json.loads(text[6:])
            if last.get("type") == "text":
                streamed += last.get("text", "")
                if first is None and last.get("text", "").strip():
                    first = time.monotonic() - t0
    return first, time.monotonic() - t0, last, streamed


def chat_check(api: Api, repeat: int, same: str | None) -> int:
    """Whole answers (P0 01.10: an answer cut mid-word): ``repeat`` questions ru/kk (or ``same`` asked ``repeat``
    times); per reply the first words, the end of the stored text, the providers, finish reasons, ``truncated`` and
    where the clarifying question stands. Exit 1 if any reply is cut, missing or not ending as a whole sentence."""
    qs = [("ru", same)] * repeat if same else [CHECK_QUESTIONS[i % len(CHECK_QUESTIONS)] for i in range(repeat)]
    bad, firsts, totals, q_mid = 0, [], [], 0
    for n, (lang, q) in enumerate(qs, 1):
        first, total, last, streamed = _ask(api, lang, q)
        d = last.get("diagnostics") or {}
        timing = d.get("timing") or {}
        text = ((last.get("message") or {}).get("text") or "").replace("[[DOCUMENT]]", "").strip()
        short, _, details = text.partition("[[MORE]]")
        cut = timing.get("truncated")
        whole = text.rstrip().endswith(_END)
        # the clarifying question: should be the last sentence of the reply, never in the middle
        mid = "?" in short and details.strip() and not details.rstrip().endswith("?")
        q_mid += bool(mid)
        ok = last.get("type") == "done" and whole and not cut
        bad += not ok
        if first is not None:
            firsts.append(first)
        totals.append(total)
        rounds = "; ".join(f"{x.get('provider')}:{x.get('stop')}" + (f"/{x.get('finish')}" if x.get('finish') else "")
                           for x in timing.get("rounds", []))
        print(f"{'ok ' if ok else 'BAD'} #{n:02d} [{lang}] first {'—' if first is None else f'{first:.2f}'} s · total "
              f"{total:.1f} s · by {d.get('served_by')} · rounds [{rounds}] · truncated {cut or '-'} · chars "
              f"{len(text)} (streamed {len(streamed)}) · question "
              f"{'MIDDLE' if mid else 'end' if text.rstrip().endswith('?') else '-'} · "
              f"{q[:34]}")
        print(f"      starts «{text[:70]}» … ends «{text[-60:]}»".replace("\n", " "))
        if last.get("type") != "done":
            print(f"      {last}")
    firsts.sort()
    totals.sort()
    if firsts:
        print(f"first words: median {firsts[len(firsts) // 2]:.2f} s · max {firsts[-1]:.2f} s · total median "
              f"{totals[len(totals) // 2]:.1f} s · n={len(qs)} · cut/missing {bad} · question in the middle {q_mid}")
    return 1 if bad or not firsts else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--chat-check", type=int, metavar="N", help="N chat replies ru/kk: none may be cut")
    ap.add_argument("--same", help="with --chat-check: ask this one question N times")
    ap.add_argument("--api", default="https://api.konsilier.com")
    ap.add_argument("--story", default=STORY)
    ap.add_argument("--chat-speed", action="store_true", help="only the chat: first words of 10 ru/kk questions")
    ap.add_argument("--path3", action="store_true", help="the 3-minute path: question → document for 3 cases")
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
    if args.chat_check:
        return chat_check(api, args.chat_check, args.same)
    if args.path3:
        return path3(api, boot)

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
