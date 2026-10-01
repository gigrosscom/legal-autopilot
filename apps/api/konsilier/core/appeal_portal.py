"""Manual filing on the country's official appeal portal (pack data ``packs/<cc>/appeal_portal.yaml``): which steps
are filed there, what to choose in the portal's form, reading the appeal number and date from the portal's
confirmation, and the JSON of a filing record. See ``api/appeal_portal.py``.
"""

from __future__ import annotations

import logging
import re
from datetime import date
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from .llm.base import Attachment, LLMError
from .models import Action, Filing

if TYPE_CHECKING:
    from .packs import AppealPortalGuide, JurisdictionPack

log = logging.getLogger(__name__)


def _host(url: str | None) -> str:
    return (urlparse(url).hostname or "").removeprefix("www.") if url else ""


def portal_target(pack: "JurisdictionPack", lang: str, action: Action) -> dict[str, Any] | None:
    """What to pick on the appeal portal for this step, or None when the document is not filed there."""
    guide = pack.appeal_portal
    if guide is None or action.kind != "document":
        return None
    addressee = action.addressee or {}
    rec = guide.for_addressee(addressee)
    if rec is None and _host(addressee.get("submit_url")) != _host(guide.portal):
        return None
    lang = pack.lang(lang)
    return {
        "channel": guide.channel,
        "name": guide.name,
        "portal": guide.portal,
        "body": addressee.get("name") or "",
        "body_key": f"{addressee['kind']}:{addressee['key']}" if addressee.get("key") else None,
        "recipient": pack.localized(rec.recipient, lang) if rec else None,
        "appeal_type": rec.appeal_type if rec else None,
        "category": pack.localized(rec.category, lang) if rec else None,
        "verified": bool(rec and rec.verified_on),
    }


def filing_record(f: Filing) -> dict[str, Any]:
    return {"id": str(f.id), "channel": f.channel, "body": f.body, "appeal_type": f.appeal_type,
            "category": f.category, "number": f.external_id, "filed_at": f.filed_at.isoformat(),
            "receipt_evidence_id": str(f.receipt_evidence_id) if f.receipt_evidence_id else None,
            "doc_sha256": f.doc_sha256, "doc_format": f.doc_format, "source": f.source,
            "created_at": f.created_at.isoformat() if f.created_at else None}


# ---------------------------------------------------------------- reading the portal's confirmation
_DATE = re.compile(r"\b(\d{1,2})[./](\d{1,2})[./](\d{4})\b|\b(\d{4})-(\d{2})-(\d{2})\b")


def _dates(text: str) -> list[tuple[int, date]]:
    out = []
    for m in _DATE.finditer(text):
        try:
            d = date(int(m[3]), int(m[2]), int(m[1])) if m[1] else date(int(m[4]), int(m[5]), int(m[6]))
        except ValueError:
            continue
        out.append((m.start(), d))
    return out


def find_number_and_date(guide: "AppealPortalGuide", text: str, today: date) -> tuple[str | None, date | None]:
    """The appeal number and the filing date in the portal's confirmation (SMS, e-mail, PDF, text of a screenshot).

    The number is found by the pack's ``proof.number_pattern`` (group 1, must hold a digit); the date is the first
    valid date after the number («№ … от 01.10.2026»), else the first one in the text — never a future date."""
    number, at = None, 0
    for m in re.finditer(guide.proof.number_pattern, text, re.IGNORECASE):
        cand = m.group(1).strip(" .-/")
        if re.search(r"\d", cand) and not _DATE.fullmatch(cand):
            number, at = cand, m.end()
            break
    found = [(pos, d) for pos, d in _dates(text) if d <= today]
    after = [d for pos, d in found if pos >= at]
    filed = after[0] if after else (found[0][1] if found else None)
    return number, filed


def read_filing_proof(llm: Any, guide: "AppealPortalGuide", lang: str, text: str | None,
                      attachments: tuple[Attachment, ...], today: date) -> dict[str, Any]:
    """Number and date from the confirmation: first the text itself, then — for a photo or a scan — the model.
    Returns ``{"number", "filed_on", "source"}``; ``source`` is ``text``, ``model`` or None (nothing found)."""
    number, filed = find_number_and_date(guide, text, today) if text else (None, None)
    if number and filed:
        return {"number": number, "filed_on": filed, "source": "text"}
    source = "text" if (number or filed) else None
    if attachments:
        schema = {"type": "object", "additionalProperties": False, "required": ["number", "date"],
                  "properties": {"number": {"type": ["string", "null"]}, "date": {"type": ["string", "null"]}}}
        system = (f"Task: the image or PDF is a confirmation from the {guide.name} appeal portal (a screenshot, an "
                  "SMS, an e-mail or a receipt). Return the registration number of the appeal exactly as written "
                  "and the date it was filed or registered as YYYY-MM-DD. Only what is literally shown; null "
                  "otherwise. Do not invent.")
        try:
            out = llm.complete_json(task="extract_filing_proof", system=system,
                                    payload={"text": text or "", "language": lang, "portal": guide.name},
                                    schema=schema, attachments=attachments)
        except LLMError as e:
            log.warning("extract_filing_proof failed: %s", e)
            out = {}
        m_number = str(out.get("number") or "").strip() or None
        if m_number and (not re.search(r"\d", m_number) or len(m_number) > 64):
            m_number = None
        ds = _dates(str(out.get("date") or ""))
        m_date = ds[0][1] if ds and ds[0][1] <= today else None
        if (m_number and not number) or (m_date and not filed):
            number, filed, source = number or m_number, filed or m_date, "model"
    return {"number": number, "filed_on": filed, "source": source}
