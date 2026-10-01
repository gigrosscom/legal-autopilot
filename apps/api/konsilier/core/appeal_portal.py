"""Manual filing on the country's official appeal portal (pack data ``packs/<cc>/appeal_portal.yaml``): which steps
are filed there, what to choose in the portal's form, and the JSON of a filing record. See ``api/appeal_portal.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from .models import Action, Filing

if TYPE_CHECKING:
    from .packs import JurisdictionPack


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
