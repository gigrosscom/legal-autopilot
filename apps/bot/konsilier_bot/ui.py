"""Pure rendering of a case into bot text + buttons (easy to unit-test)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .i18n import t

Button = tuple[str, str]  # (label, callback_data)


@dataclass
class Screen:
    text: str
    buttons: list[list[Button]] = field(default_factory=list)
    document_action: dict[str, Any] | None = None  # action whose file should be sent


def last_action(case: dict[str, Any]) -> dict[str, Any] | None:
    return case["actions"][-1] if case.get("actions") else None


def payment_text(pay: dict[str, Any], lang: str) -> str:
    """Where and how much to transfer for the document; the status line after "I have paid"."""
    amount = f"{pay['amount']:,.0f}".replace(",", " ")
    if pay["status"] == "awaiting_confirmation":
        return t("payment_waiting", lang, code=pay["code"])
    text = t("payment", lang, amount=amount, currency=pay.get("currency") or "", name=pay.get("recipient_name") or "",
             phone=pay.get("kaspi_phone") or "", code=pay["code"])
    return t("payment_not_found", lang, code=pay["code"]) + "\n\n" + text if pay["status"] == "not_found" else text


def case_screen(case: dict[str, Any], message: str | None = None) -> Screen:
    lang = case.get("language", "ru")
    cid = case["id"]
    parts: list[str] = [message] if message else []
    buttons: list[list[Button]] = []
    doc: dict[str, Any] | None = None
    status = case["status"]
    proposal = case.get("proposal") or {}
    action = last_action(case)

    coverage = case.get("coverage") or {}
    safety = case.get("safety") or {}
    if status == "intake" and coverage.get("options") and not case.get("scenario"):
        # universal path: the user chooses where to file (index keeps callback data short)
        for i, opt in enumerate(coverage["options"]):
            buttons.append([(opt["name"][:60], f"forum:{cid}:{i}")])
    elif status == "intake" and safety.get("pending_ack"):
        kind = safety["pending_ack"]
        buttons.append([(t(f"buttons.ack_{kind}", lang), f"ack:{cid}:{kind}")])
    elif status == "intake":
        q = case.get("question")
        if q and not message:
            parts.append(q["text"])
        if q and q.get("optional"):
            buttons.append([(t("buttons.skip", lang), f"skip:{cid}")])
    elif status == "qualified":
        pay = case.get("payment") or {}
        if pay.get("status") in ("pending", "awaiting_confirmation", "not_found"):
            parts.append(payment_text(pay, lang))
            if pay["status"] != "awaiting_confirmation":
                buttons.append([(t("buttons.paid", lang), f"paid:{cid}")])
        buttons.append([(t("buttons.prepare", lang), f"prep:{cid}")])
    elif status == "action_ready" and action:
        if action["approval_status"] in ("pending", "rejected"):
            parts.append(t("awaiting_approval", lang))
        elif action.get("downloadable", True):
            doc = action
            steps = "\n".join(f"{i}. {s}" for i, s in enumerate(action["instructions"], 1))
            parts.append(f"{t('instructions', lang)}\n{steps}")
            row = [(t("buttons.submitted", lang), f"sub:{cid}")]
            if action.get("email_allowed") and (action.get("addressee") or {}).get("email"):
                row.append((t("buttons.email", lang), f"mail:{cid}"))
            buttons.append(row)
    elif status == "awaiting_response" and action:
        dl = action.get("deadline")
        if dl and not message:
            parts.append(t("deadline", lang, date=date.fromisoformat(dl["due_date"]).strftime("%d.%m.%Y")))
        ptype = proposal.get("type")
        if ptype == "clarify":
            buttons.append([(t(f"buttons.{c}", lang), f"cls:{cid}:{c}") for c in ("full", "partial")])
            buttons.append([(t(f"buttons.{c}", lang), f"cls:{cid}:{c}") for c in ("refusal", "none")])
        elif ptype == "prepare_action":
            buttons.append([(t("buttons.prepare", lang), f"prep:{cid}")])
        elif ptype == "handoff":
            buttons.append([(t("buttons.handoff", lang), f"prep:{cid}")])
        elif ptype == "close":
            pass
        else:
            buttons.append([(t("buttons.got_response", lang), f"resp:{cid}"),
                            (t("buttons.no_response", lang), f"none:{cid}")])
        if ptype in ("close", "prepare_action", "handoff"):
            buttons.append([(t("buttons.close_won", lang), f"close:{cid}:won")])
            buttons.append([(t("buttons.close_partial", lang), f"close:{cid}:partial"),
                            (t("buttons.close_lost", lang), f"close:{cid}:lost")])
    elif status == "resolved":
        parts.append(t("case_closed", lang))
    if proposal.get("message") and proposal["message"] not in parts and status != "intake":
        parts.append(proposal["message"])
    if not parts:
        parts.append(t("status", lang, status=case.get("status_label", status)))
    return Screen(text="\n\n".join(p for p in parts if p), buttons=buttons, document_action=doc)
