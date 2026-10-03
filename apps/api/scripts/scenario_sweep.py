"""Scenario sweep: the real chat over a matrix of client dialogs, with the transcripts and the draft document collected
into a readable report for the lawyer (ZANN) and the editor (PM 03.10, quality pilot — family law first).

Each case of the matrix (tests/data/sweeps/<domain>.yaml) is played through the whole app in-process — the real chat
model, the production prompt and rules, the server's gates, classification and the draft — never mocks:
POST /v1/cases → POST /chat for every turn → GET /draft. The report holds, per branch: the scenario chosen, every
reply (whether the document card was shown), the request for documents, and the document's title with its first lines.

    cd apps/api && QA_GEMINI_API_KEY=… python3 scripts/scenario_sweep.py family
    SWEEP_ONLY=F1,F3 python3 scripts/scenario_sweep.py family
    SWEEP_REPORT=../../qa-reports/2026-10-03/scenario-sweep-family.md python3 scripts/scenario_sweep.py family

Without a key (SWEEP_MODE=interview, the default when QA_GEMINI_API_KEY is not set): no model at all — the server's
own interview (its questions, gates and classification by words), the heuristic extractor of the tests, the document
from the pack's templates; the test payment stub opens the document, as in the test suite. The chat model's replies
are then not in the report — only what the server itself says and the document it makes.

Keys: only the QA ones (QA_GEMINI_API_KEY, optional QA_GROQ_API_KEY, QA_CEREBRAS_API_KEY) — never the production
keys (their free daily quota is the clients'), never a paid model. Without a QA key the sweep does not start.
Any domain is a new YAML of the same shape; nothing here is family-specific.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from datetime import date
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

API = Path(__file__).resolve().parents[1]
ROOT = API.parents[1]
MATRICES = API / "tests" / "data" / "sweeps"
ADMIN_TOKEN = "sweep"  # the in-process app's own desk token: the sweep reads a court document as /ops does


def _sse(resp: Any) -> list[dict[str, Any]]:
    return [json.loads(line[6:]) for line in resp.text.splitlines() if line.startswith("data: ")]


def mode() -> str:
    return os.environ.get("SWEEP_MODE") or ("chat" if os.environ.get("QA_GEMINI_API_KEY") else "interview")


def settings_for_sweep(tmp: Path) -> Any:
    from konsilier.config import Settings

    if mode() == "interview":
        return Settings(
            database_url=f"sqlite:///{tmp}/sweep.db", packs_dir=ROOT / "packs", storage_backend="local",
            storage_local_dir=tmp / "files", llm_provider="mock", gemini_api_key="", groq_api_key="",
            cerebras_api_key="", anthropic_api_key=None, soffice_bin="", admin_token=ADMIN_TOKEN,
            scheduler_interval_seconds=0, background_jobs="inline", resend_api_key=None, smtp_host=None,
            payment_mode="stub", payment_requires_contact=False, approval_required_first_n=0)
    key = os.environ.get("QA_GEMINI_API_KEY", "")
    if not key:
        raise SystemExit("QA_GEMINI_API_KEY is not set: the sweep runs on its own QA key, never on the production one")
    return Settings(
        database_url=f"sqlite:///{tmp}/sweep.db", packs_dir=ROOT / "packs", storage_backend="local",
        storage_local_dir=tmp / "files", llm_provider="gemini", gemini_api_key=key,
        groq_api_key=os.environ.get("QA_GROQ_API_KEY", ""), cerebras_api_key=os.environ.get("QA_CEREBRAS_API_KEY", ""),
        anthropic_api_key=None,  # never a paid model from a sweep
        soffice_bin="", admin_token=ADMIN_TOKEN, scheduler_interval_seconds=0, background_jobs="inline",
        resend_api_key=None, smtp_host=None, payment_requires_contact=False, chat_daily_limit=1000,
    )


def play(client: Any, case: dict[str, Any]) -> dict[str, Any]:
    token = client.post("/v1/users", json={"language": case.get("language", "ru")}).json()["token"]
    h = {"Authorization": f"Bearer {token}"}
    turns = case["turns"]
    created = client.post("/v1/cases", headers=h, json={"text": turns[0], "country": case.get("country", "KZ"),
                                                         "defer": True})
    cid = created.json()["case"]["id"]
    log: list[dict[str, Any]] = []
    for text in turns:
        t0 = time.perf_counter()
        events = _sse(client.post(f"/v1/cases/{cid}/chat", headers=h, json={"text": text}))
        done = next((e for e in reversed(events) if e.get("type") == "done"), {})
        msg = done.get("message") or {}
        error = next((e.get("code") for e in events if e.get("type") == "error"), None)
        log.append({"user": text, "bot": msg.get("text") or "", "offer": bool(msg.get("offer_document")),
                    "asked_documents": bool(msg.get("asked_documents")), "error": error,
                    "ms": int((time.perf_counter() - t0) * 1000)})
    view = client.get(f"/v1/cases/{cid}", headers=h).json()
    draft = client.get(f"/v1/cases/{cid}/draft", headers=h)
    visible = (draft.json().get("visible") or "") if draft.status_code == 200 else ""
    card = client.get(f"/v1/cases/{cid}/chat/document", headers=h).json()
    return {"case": case, "scenario": (view.get("scenario") or {}).get("id"), "status": view.get("status"),
            "card": card, "log": log, "draft": visible, "draft_status": draft.status_code}


def play_interview(client: Any, case: dict[str, Any]) -> dict[str, Any]:
    """No model: the server's interview with the client's words, then the document made from the pack's template."""
    from konsilier.core.documents import docx_text

    token = client.post("/v1/users", json={"language": case.get("language", "ru")}).json()["token"]
    h = {"Authorization": f"Bearer {token}"}
    turns = case["turns"]
    t0 = time.perf_counter()
    first = client.post("/v1/cases", headers=h, json={"text": turns[0], "country": case.get("country", "KZ")}).json()
    cid = first["case"]["id"]
    log = [{"user": turns[0], "bot": (first.get("reply") or {}).get("message") or "", "offer": False,
            "asked_documents": False, "error": None, "ms": int((time.perf_counter() - t0) * 1000)}]
    for text in turns[1:]:
        t0 = time.perf_counter()
        r = client.post(f"/v1/cases/{cid}/messages", headers=h, json={"text": text})
        body = r.json() if r.status_code == 200 else {}
        log.append({"user": text, "bot": (body.get("reply") or {}).get("message") or "", "offer": False,
                    "asked_documents": False, "error": None if r.status_code == 200 else str(r.status_code),
                    "ms": int((time.perf_counter() - t0) * 1000)})
    document = ""
    for _ in range(3):  # the form before payment: what the interview left blank gets a visible stand-in value
        pay = client.post(f"/v1/cases/{cid}/payment", headers=h, json={"purpose": "document"})
        if pay.status_code != 422 or pay.json()["detail"].get("code") != "applicant_data_required":
            break
        client.post(f"/v1/cases/{cid}/facts", headers=h, json={"values": {
            f["field"]: stand_in(f) for f in pay.json()["detail"]["fields"]}})
    for _ in range(3):  # «Составить документ» asks the same form when the payment did not
        nxt = client.post(f"/v1/cases/{cid}/actions/next", headers=h)
        if nxt.status_code != 422 or nxt.json()["detail"].get("code") != "applicant_data_required":
            break
        client.post(f"/v1/cases/{cid}/facts", headers=h, json={"values": {
            f["field"]: stand_in(f) for f in nxt.json()["detail"]["fields"]}})
    view = client.get(f"/v1/cases/{cid}", headers=h).json()
    if nxt.status_code == 200 and view.get("actions"):
        a = view["actions"][0]
        # a court document waits for the lawyer's check before the client may download it: the sweep reads it as the
        # desk does (/ops), the text being what the lawyer and the editor review
        got = client.get(f"/v1/admin/actions/{a['id']}/document", headers={"X-Admin-Token": ADMIN_TOKEN},
                         params={"format": "docx"})
        document = docx_text(got.content) if got.status_code == 200 else f"(документ не прочитан: {got.status_code})"
        if a.get("status") == "pending_approval":
            document = "[ждёт проверки юриста перед выдачей клиенту]\n" + document
    else:
        document = f"(документ не создан: {nxt.status_code} {nxt.text[:200]})"
    return {"case": case, "scenario": (view.get("scenario") or {}).get("id"), "status": view.get("status"),
            "card": {"title": (view.get("actions") or [{}])[0].get("title")}, "log": log, "draft": document,
            "draft_status": nxt.status_code}


STAND_IN = {"date": "01.09.2026", "money": "100000", "phone": "+7 700 000 00 00"}


def stand_in(f: dict[str, Any]) -> str:
    """A plausible value the sweep types in place of the client in the form before payment (marked in the report)."""
    n = f["field"]
    if f["type"] in STAND_IN:
        return STAND_IN[f["type"]]
    if n.endswith("address"):
        return "г. Алматы, ул. Абая, 10, кв. 5"
    if n.endswith(("iin", "bin")):
        return "880101300123"
    if n.endswith("email"):
        return "client@example.kz"
    if n == "applicant_name":
        return "Иванова Анна Сергеевна"
    if n.endswith("name"):
        return "Иванов Сергей Петрович"
    return "[для прогона: " + f["label"] + "]"


def report(matrix: dict[str, Any], results: list[dict[str, Any]]) -> str:
    how = ("реальный чат (QA-ключ), без моков" if mode() == "chat" else
           "без модели: вопросы и проверки сервера, извлечение — эвристика тестов, документ — шаблон пака; "
           "ФИО, адреса, телефон «Иванова Анна Сергеевна», «г. Алматы, ул. Абая, 10» и [для прогона: …] подставил прогонщик "
           "вместо клиента в форме перед оплатой")
    out = [f"# Прогон матрицы — {matrix.get('title', matrix['domain'])}", "",
           f"{date.today().isoformat()} · {how} · веток: {len(results)}", "",
           "| Ветка | Сценарий | Статус | Карточка документа | Документ |", "|---|---|---|---|---|"]
    for r in results:
        title = (r["card"] or {}).get("title") or "—"
        offered = "да" if any(t["offer"] for t in r["log"]) else "нет"
        out.append(f"| {r['case']['id']} {r['case'].get('branch', '')} | {r['scenario'] or '—'} | {r['status']} | "
                   f"{offered} | {title} |")
    for r in results:
        out += ["", f"## {r['case']['id']}. {r['case'].get('branch', '')}", "",
                f"Сценарий: `{r['scenario'] or '—'}` · статус: {r['status']}", ""]
        for i, t in enumerate(r["log"], start=1):
            flags = ", ".join(x for x, on in (("карточка", t["offer"]), ("просьба о документах", t["asked_documents"]),
                                               (f"ошибка {t['error']}", bool(t["error"]))) if on)
            out += [f"**Клиент {i}:** {t['user']}", "", f"**Бот {i}**" + (f" ({flags})" if flags else "") +
                    f" · {t['ms']} мс:", "", t["bot"].strip() or "_(пусто)_", ""]
        lines = [ln for ln in r["draft"].splitlines() if ln.strip()]
        if mode() == "chat":
            lines = lines[:12]
        out += ["**Документ:**" if mode() == "interview" else "**Документ (черновик, первые строки):**", "", "```",
                *(lines or ["(документа нет)"]), "```"]
    return "\n".join(out) + "\n"


def main() -> int:
    domain = sys.argv[1] if len(sys.argv) > 1 else "family"
    matrix = yaml.safe_load((MATRICES / f"{domain}.yaml").read_text("utf-8"))
    only = {x.strip() for x in os.environ.get("SWEEP_ONLY", "").split(",") if x.strip()}
    cases = [c for c in matrix["cases"] if not only or c["id"] in only]
    from fastapi.testclient import TestClient

    from konsilier.container import build_container
    from konsilier.core.models import Base
    from konsilier.main import create_app

    if mode() == "interview":
        from konsilier.core import ai

        def no_model(*_a: Any, **_k: Any) -> Any:
            raise RuntimeError("no model in the sweep: the scenario is chosen by its keywords, as when the model is down")
        ai.qualify = no_model  # the tests' heuristic would pick «refund» for «квартира, купленная в браке»
    with tempfile.TemporaryDirectory() as tmp:
        settings = settings_for_sweep(Path(tmp))
        container = build_container(settings)
        Base.metadata.create_all(container.engine_db)
        app = create_app(settings, container, start_scheduler=False)
        with TestClient(app) as client:
            run = play if mode() == "chat" else play_interview
            results = [run(client, c) for c in cases]
    text = report(matrix, results)
    path = os.environ.get("SWEEP_REPORT") or str(ROOT / "qa-reports" / date.today().isoformat()
                                                  / f"scenario-sweep-{domain}.md")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text, "utf-8")
    print(f"{len(results)} branches → {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
