"""Anonymisation of court texts before any training use and before any transfer abroad (NVIDIA, Kaggle, Hugging
Face …). Owner's decision 01.10.2026: court practice is collected as it is published, kept on our own server, and
only anonymised texts ever leave it.

Rule based, no network, no model. The rules are the country's data — ``packs/<cc>/zann/anonymize.yaml``: the
labels, the alphabet, name endings and role words, the national id number, phone / plate / account / document /
case-number formats, address words. This module only applies them. Every hit becomes a label numbered within the
document; the same person, number or address gets the same label everywhere in that document:

    person      full names, «Surname I.N.», «I.N. Surname», role word + surname, and every later case form of a
                surname found once (the stem without the pack's case endings)
    id_person / id_org   national id numbers; an organisation's number is kept only when it is clearly one (the
                pack's organisation structure, its keyword just before it and a legal form nearby), else masked
    address, phone, email, document, case, plate, account, birth

City and court names, statutes, sums and dates of the case are kept: they are what the model learns from.
``anonymize(text, rules)`` returns the text and a report (counts by label; never the replaced values).
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

KINDS = ("person", "id_person", "id_org", "address", "phone", "email", "document", "case", "plate", "account", "birth")


def rules_path(packs_dir: Path, country: str) -> Path:
    return Path(packs_dir) / country.lower() / "zann" / "anonymize.yaml"


@lru_cache(maxsize=16)
def load_rules(packs_dir: Path, country: str) -> "Rules":
    """The anonymisation rules of a country pack (packs/<cc>/zann/anonymize.yaml)."""
    path = rules_path(packs_dir, country)
    if not path.is_file():
        raise FileNotFoundError(f"zann anonymize: no rules for {country!r} ({path})")
    return Rules(yaml.safe_load(path.read_text("utf-8")))


class Rules:
    """Compiled patterns of one country. Fragments come from the pack; the shapes of names are composed here."""

    def __init__(self, data: dict[str, Any]):
        self.labels: dict[str, str] = {k: str(data["labels"][k]) for k in KINDS}
        up, lo = data["letters"]["upper"], data["letters"]["lower"]
        self.up, self.lo = up, lo
        n = data["names"]
        pat_end, split_end = n["patronymic_end"], n["patronymic_split_end"]
        self.surname_end, self.case_end = n["surname_end"], n["case_end"]
        self.stem_endings = sorted(n["stem_endings"], key=len, reverse=True)
        self.stop = {w.lower() for w in n["stop_words"]}
        role, place_after = n["role"], n["place_after"]

        cap = rf"[{up}][{lo}]+(?:-[{up}][{lo}]+)?"  # a capitalised word, double-barrelled allowed
        patronymic = rf"[{up}][{lo}]+{pat_end}(?![{lo}])"
        patronymic_split = rf"[{up}][{lo}]+\s{split_end}(?![{lo}])"
        sp = r"[ \t\xa0]"  # a space on the same line: names never run across a line break
        i1, i2 = rf"[{up}]\.", rf"[{up}]\.{sp}?[{up}]\."
        surname = rf"{cap}{self.surname_end}{self.case_end}"
        nb = rf"(?<![{up}{lo}])"
        self.cap = re.compile(rf"{nb}{cap}(?![{lo}])")
        self.role_word = re.compile(role)
        self.surname_shape = re.compile(rf"{self.surname_end}{self.case_end}$")
        # (pattern, the surname may be propagated to its other forms)
        self.fio = [
            (re.compile(rf"{nb}({cap})\s+{cap}\s+(?:{patronymic}|{patronymic_split})"), True),  # Surname Name Patr.
            (re.compile(rf"{nb}{cap}\s+(?:{patronymic})\s+({surname})(?![{lo}])"), True),       # Name Patr. Surname
            (re.compile(rf"{nb}({cap}){sp}?{i2}"), True),                                          # Surname I.N.
            (re.compile(rf"{nb}({surname}){sp}?{i1}(?!{sp}?[{up}][{lo}])"), True),                 # Surname I.
            (re.compile(rf"(?<![{up}{lo}.]){i2}{sp}?({cap})(?![{lo}]){place_after}"), True),       # I.N. Surname
            (re.compile(rf"(?<![{up}{lo}.]){i1}{sp}?({surname})(?![{lo}]){place_after}"), True),  # I. Surname
            (re.compile(rf"{nb}(){cap}\s+(?:{patronymic}|{patronymic_split})"), False),            # Name Patr.
        ]
        place_ahead = place_after.replace("(?!", "(?=", 1)
        self.role_fio = re.compile(
            rf"{nb}{role}\s+(?:\(?[{lo}]+\)?\s+)?({cap})"
            rf"(?:\s+(?!{cap}{place_ahead}){cap}(?:\s+(?:{patronymic}|{patronymic_split}))?)?(?![{lo}])")

        nid = data["national_id"]
        self.national_id = re.compile(nid["pattern"])
        self.org_pos, self.org_digits = int(nid["org_digit_position"]), str(nid["org_digits"])
        self.org_keyword = re.compile(nid["org_keyword_before"])
        self.org_forms = re.compile(nid["org_forms"])

        p = data["patterns"]
        self.p = {k: re.compile(v) for k, v in p.items()}
        a = data["address"]
        self.address = re.compile(rf"(?:{a['street_word']}\s*{a['street_name']}|[{up}][{lo}]+(?:\s[{up}][{lo}]+)?\s+"
                                  rf"{a['street_word']}){a['house_part']}*")
        self.label_re = re.compile(r"\[(?:" + "|".join(map(re.escape, self.labels.values())) + r")\d+\]")

    def stem(self, word: str) -> str:
        """A surname without a case ending: the same person in every grammatical case."""
        w = word.lower()
        for end in self.stem_endings:
            if w.endswith(end) and len(w) - len(end) >= 3:
                return w[: -len(end)]
        return w

    def id_kind(self, digits: str, before: str) -> str | None:
        """id_person or id_org for a national id number, None to keep it (clearly an organisation's)."""
        if len(digits) <= self.org_pos or digits[self.org_pos] not in self.org_digits:
            return "id_person"
        if self.org_keyword.search(before[-20:]) and self.org_forms.search(before[-160:]):
            return None
        return "id_org"


@dataclass
class Report:
    counts: Counter = field(default_factory=Counter)  # label → replaced occurrences

    @property
    def total(self) -> int:
        return sum(self.counts.values())


class Anonymizer:
    """One document at a time: ``Anonymizer(rules).run(text)``. Labels are numbered per instance (per document)."""

    def __init__(self, rules: Rules) -> None:
        self.r = rules
        self.labels: dict[tuple[str, str], str] = {}
        self.next: Counter = Counter()
        self.report = Report()

    def label(self, kind: str, key: str) -> str:
        name = self.r.labels[kind]
        k = (kind, key)
        if k not in self.labels:
            self.next[kind] += 1
            self.labels[k] = f"[{name}{self.next[kind]}]"
        self.report.counts[name] += 1
        return self.labels[k]

    # ---- span collection
    def _spans(self, text: str) -> list[tuple[int, int, str, str]]:
        r, p = self.r, self.r.p
        spans: list[tuple[int, int, str, str]] = []

        def add(a: int, b: int, kind: str, key: str) -> None:
            if b > a:
                spans.append((a, b, kind, key))

        for m in p["email"].finditer(text):
            add(m.start(), m.end(), "email", m.group().lower())
        for m in p["iban"].finditer(text):
            add(m.start(), m.end(), "account", re.sub(r"\s", "", m.group()))
        for m in p["account"].finditer(text):
            digits = re.sub(r"\D", "", m.group(1))
            if len(digits) >= 10:
                add(m.start(1), m.end(1), "account", digits)
        for m in p["card"].finditer(text):
            add(m.start(), m.end(), "account", re.sub(r"\D", "", m.group()))
        for m in p["case"].finditer(text):
            g = 1 if m.lastindex and m.group(1) else 0
            add(m.start(g), m.end(g), "case", m.group(g))
        for m in p["document"].finditer(text):
            add(m.start(1), m.end(1), "document", re.sub(r"\s", "", m.group(1)))
        for m in r.national_id.finditer(text):
            kind = r.id_kind(m.group(), text[:m.start()])
            if kind:
                add(m.start(), m.end(), kind, m.group())
        for m in p["phone"].finditer(text):
            digits = re.sub(r"\D", "", m.group())
            if len(digits) >= 7:
                add(m.start(), m.end(), "phone", digits[-10:])
        for m in p["birth"].finditer(text):
            add(m.start(), m.end(), "birth", m.group())
        for m in p["plate"].finditer(text):
            if p["plate_context"].search(text[max(0, m.start() - 80):m.start()]) and re.search(r"\d", m.group()) \
                    and re.search(rf"[A-Z{r.up}]", m.group()):
                add(m.start(), m.end(), "plate", re.sub(r"\s", "", m.group()).upper())
        for m in r.address.finditer(text):
            if re.search(r"\d", m.group()) or len(m.group()) > 8:
                add(m.start(), m.end(), "address", re.sub(r"\s+", " ", m.group().lower()))
        for m in p["house_only"].finditer(text):
            add(m.start(), m.end(), "address", re.sub(r"\s+", " ", m.group().lower()))
        self._names(text, add)
        return spans

    def _names(self, text: str, add) -> None:
        r = self.r
        surnames: set[str] = set()
        for rx, propagate in r.fio:
            for m in rx.finditer(text):
                sur = m.group(1)
                if sur and (sur.lower() in r.stop or r.role_word.fullmatch(sur)):
                    continue
                if not sur and any(w.lower() in r.stop for w in m.group().split()):
                    continue
                key = r.stem(sur) if sur else m.group().lower()
                if sur and propagate:
                    surnames.add(key)
                add(m.start(), m.end(), "person", key)
        for m in r.role_fio.finditer(text):
            sur = m.group(1)
            if sur.lower() in r.stop or r.role_word.fullmatch(sur) or (
                    not r.surname_shape.search(sur) and m.end() == m.end(1)):
                continue
            key = r.stem(sur)
            surnames.add(key)
            add(m.start(1), m.end(), "person", key)
        if not surnames:
            return
        for m in r.cap.finditer(text):  # every later form of a found surname
            w = m.group()
            if w.lower() not in r.stop and r.stem(w) in surnames:
                add(m.start(), m.end(), "person", r.stem(w))

    def run(self, text: str) -> str:
        spans = sorted(self._spans(text), key=lambda s: (s[0], -(s[1] - s[0])))
        out, pos = [], 0
        for a, b, kind, key in spans:
            if a < pos:  # overlaps an earlier, longer hit
                continue
            out.append(text[pos:a])
            out.append(self.label(kind, key))
            pos = b
        out.append(text[pos:])
        return "".join(out)


def anonymize(text: str, rules: Rules) -> tuple[str, Report]:
    a = Anonymizer(rules)
    return a.run(text or ""), a.report


def anonymize_record(fields: dict[str, str], rules: Rules) -> tuple[dict[str, str], Report]:
    """Several fields of one document (title, text …) with one numbering, so a label is the same person in all."""
    a = Anonymizer(rules)
    return {k: a.run(v or "") for k, v in fields.items()}, a.report
