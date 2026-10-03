"""«Как подать»: where, until when and how a ready document is filed, and how long the addressee has to answer.

Everything comes from pack data — the scenario action (``deadline``, ``channel``, ``filing``), the addressee and,
on the universal path, the forum registry (``submission``, ``response_deadline``, ``filing``). Nothing is guessed:
a value the data does not hold is returned as ``None`` and the client shows «уточнит юрист».
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from . import ai
from .fields import FieldError, parse_date
from .scenario.schema import ActionSpec, FilingSpec, Scenario

if TYPE_CHECKING:
    from .coverage.schema import Forum
    from .packs import JurisdictionPack

WAYS = ("in_person", "post", "online", "email")
# forum submission kinds → filing ways shown to the person (official messengers are an online way too)
_KIND_WAY = {"portal": "online", "in_person": "in_person", "post": "post", "email": "email",
             "whatsapp": "online", "telegram": "online"}


class _Safe(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _raw(pack: "JurisdictionPack", lang: str, *path: str) -> Any:
    """A raw i18n node for ``lang`` (keys may contain dots, e.g. a portal host), falling back to the default language."""
    for candidate in (lang, pack.manifest.default_language):
        node: Any = pack.i18n.get(candidate, {})
        for part in path:
            node = node.get(part) if isinstance(node, dict) else None
        if node is not None:
            return node
    return None


def _host(url: str | None) -> str:
    return (urlparse(url).hostname or "").removeprefix("www.") if url else ""


def _known(norm_ref: str | None) -> str | None:
    """A norm reference, or None while it is still a lawyer's TODO."""
    return norm_ref if norm_ref and "TODO" not in norm_ref else None


def _ways(spec: ActionSpec, forum: "Forum | None", filing: FilingSpec | None,
          addressee: dict[str, Any]) -> list[tuple[str, str | None]]:
    """(way, url) pairs in the order the data gives them: ``filing.ways`` when a lawyer filled them in, otherwise the
    forum's submission kinds, otherwise the action channel (the same derivation as the proposed plan)."""
    portal = addressee.get("submit_url")
    if forum is not None:
        for ch in forum.submission:
            if ch.kind == "portal" and ch.url:
                portal = portal or ch.url
    out: list[tuple[str, str | None]] = []
    if filing and filing.ways:
        out = [(w, portal if w == "online" else None) for w in filing.ways]
    elif forum is not None:
        for ch in forum.submission:
            out.append((_KIND_WAY[ch.kind], ch.url if ch.kind != "email" else None))
    else:
        if portal:
            out.append(("online", portal))
        if spec.channel == "email":
            out.append(("email", None))
        elif spec.channel == "email_or_user_submits":
            out += [("in_person", None), ("post", None), ("email", None)]
        elif not out:
            out += [("in_person", None), ("post", None)]
    seen: set[str] = set()
    return [(w, u) for w, u in out if not (w in seen or seen.add(w))]


def _days(spec: Any) -> dict[str, Any]:
    return {"days": spec.calendar_days or spec.business_days,
            "unit": "calendar" if spec.calendar_days is not None else "business"}


def filing_view(pack: "JurisdictionPack", sc: Scenario, spec: ActionSpec, *, lang: str,
                addressee: dict[str, Any] | None, facts: dict[str, Any], forum: "Forum | None" = None,
                today: date | None = None) -> dict[str, Any]:
    """The «Как подать» card of one action. ``addressee`` is the dict stored on the action when it was prepared."""
    addressee = addressee or {}
    filing = spec.filing or (forum.filing if forum is not None else None)
    t = lambda key, **kw: pack.t(lang, f"filing.{key}", **kw)  # noqa: E731

    # ---- the term to answer: known before filing, counted from the day the document is received
    response = None
    rd = spec.deadline or (forum.response_deadline if forum is not None else None)
    if rd is not None:
        norm = _known(rd.norm_ref)
        response = {**_days(rd), "norm_ref": norm, "verified": norm is not None}
        if today:  # QA BUG-19: a date before filing — the answer is due by it if the document is filed today
            response["if_filed_today"] = pack.add_days(today, rd.calendar_days, rd.business_days).isoformat()

    # ---- the term to file: only when a lawyer put it into the data
    file_by = None
    fd = filing.deadline if filing else None
    if fd is not None:
        start = None
        if fd.from_field and facts.get(fd.from_field):
            try:
                start = parse_date(facts[fd.from_field])
            except FieldError:
                start = None
        due = pack.add_days(start, fd.calendar_days, fd.business_days) if start else None
        if fd.from_text:
            since = pack.localized(fd.from_text, lang)
        elif fd.from_field:
            try:
                label = ai.field_label(sc, pack, lang, fd.from_field)
            except KeyError:
                label = fd.from_field
            since = t("since_field", field=label)
        else:
            since = ""
        file_by = {**_days(fd), "date": due.isoformat() if due else None, "since": since or None,
                   "norm_ref": _known(fd.norm_ref), "verified": fd.verified,
                   "overdue": bool(due and today and due < today)}

    # ---- ways, with the details the person needs for each
    email = addressee.get("email")
    ways: list[dict[str, Any]] = []
    online = None
    for way, url in _ways(spec, forum, filing, addressee):
        host = _host(url)
        hint_key = "email_known" if way == "email" and email else way
        ways.append({"kind": way, "label": t(f"ways.{way}.label"),
                     "hint": t(f"ways.{hint_key}.hint", email=email or "", portal=host or ""),
                     "url": url})
        if way == "online" and url and online is None:
            fmt = _Safe(url=url, addressee=addressee.get("name") or "", document=pack.localized(spec.title, lang))
            devices = _raw(pack, lang, "filing", "devices", host)
            steps = {}
            if isinstance(devices, dict):
                for dev in ("phone", "desktop"):
                    lines = devices.get(dev)
                    if isinstance(lines, list):
                        steps[dev] = [str(x).format_map(fmt) for x in lines]
            online = {"portal": host, "url": url, "phone": steps.get("phone"), "desktop": steps.get("desktop"),
                      "phone_ok": bool(isinstance(devices, dict) and devices.get("phone_ok", True))}

    signature = filing.signature if filing else None
    name = addressee.get("name") or None
    if name is None and spec.addressee is not None and spec.addressee.party:
        # the other side's name is not known yet: say who it is («Работодатель»), not «уточнит юрист»
        party = sc.parties.get(spec.addressee.party)
        field = getattr(party, "name_field", None)
        if field:
            try:
                name = ai.field_label(sc, pack, lang, field)
            except KeyError:
                name = None
    return {
        "to": {"name": name, "address": addressee.get("address") or None,
               "email": email or None},
        "response": response,
        "file_by": file_by,
        "ways": ways,
        "online": online,
        "signature": signature,
        "signature_text": t(f"signature.{signature}") if signature else None,
    }
