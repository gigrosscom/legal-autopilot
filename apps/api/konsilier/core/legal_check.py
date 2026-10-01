"""Legal self-check of a document before it is given (owner 01.10, the lawyer's rules team/legal-drafts/
document-rules.md): the finished text is read against the subject of the dispute and the rules; any problem → the
document is not given, it waits for the owner's check in /ops with the reasons. Country words and norms come from
the pack (legal_check in pack.yaml); this module knows none."""
from __future__ import annotations

import re
from typing import Any

SUBJECTS = ("service", "work", "goods")


def subject_of(case: Any, sc: Any, rules: dict[str, Any]) -> str | None:
    """The dispute's subject: what the model decided when choosing the scenario, else the pack's words found in the
    story, else the scenario's only subject."""
    decided = (case.taxonomy or {}).get("subject") if isinstance(case.taxonomy, dict) else None
    if decided in SUBJECTS:
        return decided
    story = " ".join(str(x) for x in (case.initial_text, *(case.facts or {}).values()) if x).lower()
    words = rules.get("subject_words") or {}
    for subject in SUBJECTS:  # a service mentioned anywhere wins over «купил»
        if any(w.lower() in story for w in words.get(subject, ())):
            return subject
    declared = tuple(sc.classification.subject)
    return declared[0] if len(declared) == 1 else None


def check(case: Any, sc: Any, spec: Any, text: str, addressee: dict[str, Any], rules: dict[str, Any],
          currency: str, own_contacts: set[str]) -> list[str]:
    """Problems found in the finished document, in the owner's words (empty → fine)."""
    problems: list[str] = []
    subject = subject_of(case, sc, rules)
    declared = tuple(sc.classification.subject)
    if subject and declared and subject not in declared:
        problems.append(f"Предмет спора — {rules.get('subject_names', {}).get(subject, subject)}, а сценарий "
                        f"{sc.id} — о другом ({', '.join(declared)}): выбрать верный сценарий (D-19).")
    if subject in ("service", "work"):
        goods_norms = [n for n in rules.get("goods_only_norms", ()) if any(n in r for r in spec.norm_refs)]
        if goods_norms:
            problems.append(f"Для услуги указаны нормы о товаре: {', '.join(goods_norms)} (D-19).")
        bad = [w for w in rules.get("goods_only_words", ()) if re.search(rf"\b{re.escape(w)}", text, re.I)]
        if bad:
            problems.append(f"Услуга названа как товар: «{bad[0]}» (D-19).")
    applicant = sc.parties.get("applicant")
    own_id = str(case.facts.get(applicant.id_field) or "") if applicant is not None and applicant.id_field else ""
    if own_id and own_id in text and f"{sc.id}.{spec.id}" in rules.get("no_applicant_id_in", ()):
        problems.append("В этом документе указан идентификационный номер заявителя — лишние персональные данные "
                        "(D-18).")
    if re.search(r"\w\((?:а|ась|ла|на)\)", text):
        problems.append("Остались формы в скобках вроде «приобрел(а)» — род не определён.")
    if currency and re.search(rf"\d\s{re.escape(currency)}\b", text):
        problems.append(f"Сумма с кодом валюты «{currency}» вместо знака и прописи.")
    email = str(addressee.get("email") or "").strip().lower()
    if email and email in own_contacts:
        problems.append("E-mail адресата совпадает с контактом клиента.")
    annex = re.split(r"\n\s*Приложени[ея]:?\s*\n", text, maxsplit=1)
    if len(annex) == 2:
        items = [re.sub(r"^\d+\.\s*", "", line).strip() for line in annex[1].splitlines() if re.match(r"^\d+\.", line)]
        if len(items) != len(set(items)):
            problems.append("В приложениях есть повторяющиеся файлы.")
    return problems
