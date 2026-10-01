"""The other side's contacts, found in what the case already holds — «Мастер отправки» (owner 01.10.2026).

Sources, in order: the document's addressee (filled from the case), the case's facts about the other side, the
uploaded documents (receipt, contract, invoice, statement: their extracted text and facts) and the client's own
story. Plain regular expressions only: no model call and no visits to third-party sites. Every contact keeps where it
came from, so the page can say «из чека». The client's own e-mail and phone are left out.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

EMAIL = re.compile(r"[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,24}")
# +7 701 123 45 67 · 8 (727) 123-45-67 · 87011234567 · other countries in the international form
PHONE = re.compile(r"(?<![\d+])(?:\+?7|8)[\s(.-]*\d{3}[\s).-]*\d{3}[\s.-]*\d{2}[\s.-]*\d{2}(?!\d)"
                   r"|(?<![\d+])\+(?:[1-689]\d{0,2})[\s(.-]*\d{2,4}[\s).-]*\d{3,4}[\s.-]*\d{2,4}(?!\d)")


def id_pattern(labels: str) -> re.Pattern[str] | None:
    """A company registration number after one of the pack's labels («contacts.id_labels»): the labels are
    country data, so they come from the pack; 8–15 digits."""
    words = [re.escape(w.strip()) for w in labels.split("|") if w.strip()]
    if not words:
        return None
    return re.compile(r"(?:" + "|".join(sorted(words, key=len, reverse=True)) + r")\s*[:№#]?\s*(\d{8,15})(?!\d)",
                      re.IGNORECASE)
INSTAGRAM = re.compile(r"(?:instagram\.com/|instagr\.am/|ig\.me/m/)([A-Za-z0-9_.]{2,30})"
                       r"|(?:instagram|инстаграм|инстаграмм|insta|инста|inst)\s*[:\-–]?\s*@([A-Za-z0-9_.]{2,30})",
                       re.IGNORECASE)
TELEGRAM = re.compile(r"(?:t\.me/|telegram\.me/)([A-Za-z][A-Za-z0-9_]{3,31})"
                      r"|(?:telegram|телеграм|телеграмм|tg)\s*[:\-–]?\s*@([A-Za-z][A-Za-z0-9_]{3,31})", re.IGNORECASE)
WHATSAPP = re.compile(r"wa\.me/\+?(\d{10,15})", re.IGNORECASE)
SITE = re.compile(r"(?<![@\w.-])(?:https?://)?(?:www\.)?((?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
                  r"(?:kz|қаз|com|ru|net|org|shop|store|online|site|info|biz|io|app|co|uz|kg|by|ua|tr|ae|de|uk|us|eu))"
                  r"(?![\w-])(?:/[^\s,;)\"'»]*)?", re.IGNORECASE)
# not the other side: social networks and messengers (found separately), public services, our own domain
NOT_SITES = ("konsilier.", "instagram.com", "instagr.am", "t.me", "telegram.me", "wa.me", "whatsapp.com", "ig.me",
             "egov.kz", "gov.kz", "adilet.zan.kz", "google.", "apple.com", "facebook.com", "vk.com", "youtube.com",
             "tiktok.com", "gmail.com", "mail.ru", "yandex.", "w3.org")
NOT_EMAIL_DOMAINS = ("konsilier.com", "example.com")

KINDS = ("email", "phone", "whatsapp", "telegram", "instagram", "website", "bin", "address")


@dataclass
class Contact:
    kind: str
    value: str
    sources: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "value": self.value, "sources": self.sources}


def norm_phone(raw: str) -> str | None:
    digits = re.sub(r"\D", "", raw)
    if raw.strip().startswith("+"):
        return "+" + digits if 10 <= len(digits) <= 15 else None
    if len(digits) == 11 and digits[0] in "78":
        return "+7" + digits[1:]
    if len(digits) == 10 and digits[0] == "7":
        return "+7" + digits
    return None


def _site(value: str) -> str | None:
    host = value.lower().split("/")[0]
    if host.startswith("www."):
        host = host[4:]
    if any(host == d.rstrip(".") or host.startswith(d) or host.endswith("." + d.rstrip(".")) or d in host
           for d in NOT_SITES):
        return None
    if re.fullmatch(r"[\d.]+", host):
        return None
    return host


def find_in_text(text: str, ids: re.Pattern[str] | None = None) -> list[tuple[str, str]]:
    """(kind, value) pairs in a text, normalised: e-mails lower-case, phones +7…, sites as a bare host."""
    if not text:
        return []
    out: list[tuple[str, str]] = []
    emails = {m.group(0).lower().rstrip(".") for m in EMAIL.finditer(text)}
    out += [("email", e) for e in sorted(emails) if not e.endswith(NOT_EMAIL_DOMAINS)]
    rest = EMAIL.sub(" ", text)  # an e-mail's domain is not a website
    for m in WHATSAPP.finditer(rest):
        p = norm_phone("+" + m.group(1))
        if p:
            out.append(("whatsapp", p))
    for m in TELEGRAM.finditer(rest):
        out.append(("telegram", (m.group(1) or m.group(2)).lower()))
    for m in INSTAGRAM.finditer(rest):
        handle = (m.group(1) or m.group(2)).rstrip(".").lower()
        if handle not in ("p", "reel", "stories", "explore"):
            out.append(("instagram", handle))
    for m in ids.finditer(rest) if ids else ():
        out.append(("bin", m.group(1)))
    no_links = re.sub(r"wa\.me/\+?\d+", " ", rest)
    no_bins = ids.sub(" ", no_links) if ids else no_links
    for m in PHONE.finditer(no_bins):
        p = norm_phone(m.group(0))
        if p:
            out.append(("phone", p))
    for m in SITE.finditer(rest):
        host = _site(m.group(1))
        if host:
            out.append(("website", host))
    return out


class Finder:
    """Collects contacts with their sources, without repeats and without the client's own."""

    def __init__(self, own: set[str], ids: re.Pattern[str] | None = None):
        self.ids = ids
        self.own = {o.lower() for o in own if o}
        self.found: dict[tuple[str, str], Contact] = {}

    def add(self, kind: str, value: Any, source: dict[str, Any]) -> None:
        if value in (None, "") or kind not in KINDS:
            return
        v = str(value).strip()
        if kind == "email":
            v = v.lower()
            if not EMAIL.fullmatch(v) or v.endswith(NOT_EMAIL_DOMAINS):
                return
        elif kind in ("phone", "whatsapp"):
            p = norm_phone(v)
            if not p:
                return
            v = p
        elif kind == "website":
            host = _site(re.sub(r"^https?://", "", v, flags=re.IGNORECASE))
            if not host:
                return
            v = host
        elif kind in ("telegram", "instagram"):
            v = v.lstrip("@").lower()
        if v.lower() in self.own:
            return
        key = (kind, v.lower())
        c = self.found.setdefault(key, Contact(kind, v))
        if source not in c.sources and len(c.sources) < 3:
            c.sources.append(source)

    def text(self, text: str | None, source: dict[str, Any]) -> None:
        for kind, value in find_in_text(text or "", self.ids):
            self.add(kind, value, source)

    def result(self) -> list[dict[str, Any]]:
        order = {k: i for i, k in enumerate(("whatsapp", "phone", "telegram", "instagram", "email", "website",
                                             "address", "bin"))}
        wa = {c.value for c in self.found.values() if c.kind == "whatsapp"}
        found = [c for c in self.found.values() if not (c.kind == "phone" and c.value in wa)]
        return [c.to_dict() for c in sorted(found, key=lambda c: order.get(c.kind, 99))]


def _kind_of_fact(name: str) -> str | None:
    n = name.lower()
    if n.startswith(("applicant", "client", "my_", "user_")):
        return None
    for kind, words in (("email", ("email", "e_mail")), ("phone", ("phone", "tel")), ("website", ("site", "url")),
                        ("instagram", ("instagram",)), ("telegram", ("telegram",)), ("bin", ("_bin", "bin_")),
                        ("address", ("address",))):
        if any(w in n for w in words) or (kind == "bin" and n == "bin"):
            return kind
    return None


def find_contacts(case: Any, action: Any, *, own: set[str], evidence_label: Any = None,
                  id_labels: str = "") -> list[dict[str, Any]]:
    """`evidence_label(kind)`: the document kind in words («Чек или квитанция об оплате») for the source."""
    f = Finder(own, id_pattern(id_labels))
    addressee = action.addressee or {}
    src = {"type": "addressee"}
    f.add("email", addressee.get("email"), src)
    f.add("address", addressee.get("address"), src)
    if addressee.get("id") and re.fullmatch(r"\d{8,15}", str(addressee.get("id"))):
        f.add("bin", addressee.get("id"), src)
    if addressee.get("submit_url"):
        f.add("website", addressee.get("submit_url"), src)
    src = {"type": "case"}
    for name, value in (case.facts or {}).items():
        kind = _kind_of_fact(name)
        if kind and isinstance(value, (str, int)):
            f.add(kind, value, src)
    for ev in case.evidence:
        if ev.kind in ("identity", "response"):
            continue
        src = {"type": "evidence", "kind": ev.kind, "filename": ev.filename,
               "label": evidence_label(ev.kind) if evidence_label else ev.kind}
        for name, value in (ev.extracted_facts or {}).items():
            kind = _kind_of_fact(name)
            if kind and isinstance(value, (str, int)):
                f.add(kind, value, src)
        f.text(ev.text, src)
    src = {"type": "story"}
    f.text(case.initial_text, src)
    f.text(case.narrative, src)
    return f.result()
