"""Which examples may be offered as chat suggestions.

A suggestion is shown to a stranger on an empty chat screen and, when tapped, becomes their message — it reads as the
product putting words in their mouth. So suggestions must be neutral, practical tasks («Как вернуть деньги за
товар»), never a personal tragedy or an accusation («Отец умер…», «Муж избил…»).

Two word lists, matched at the start of a word in any language (they are language, not country, data):

* ``ALWAYS`` — death and violence. Never suggested, whatever topic the person chose.
* ``UNPROMPTED`` — illness and disability, divorce and ex-partners, crime victimhood, "cannot pay" debt stories,
  pregnancy. Fine once the person picked that life situation, but not in the default set shown to everyone.

Taxonomy branches in ``SENSITIVE_BRANCHES`` are left out of the default set too, except the everyday entries in
``UNPROMPTED_OK`` (child support is among the most asked-for topics; its examples are worded as a task).
Pack authors should still write examples neutrally; these lists are the safety net, not the style guide.
"""

from __future__ import annotations

import re

# Stems, matched at a word start (\b), case-insensitive. Keep them specific enough not to hit everyday words.
ALWAYS: tuple[str, ...] = (
    # ru
    "умер", "умерл", "умира", "смерт", "погиб", "скончал", "покойн", "похорон", "гибел",
    "насил", "изнасил", "избил", "избив", "избит", "бьёт", "бьет", "побои", "убий", "убил", "убьёт", "убьет",
    "суицид", "самоубий", "повесил",
    # kk
    "қайтыс", "өлді", "өлген", "өлім", "өлтір", "қаза болды", "қаза тапты", "зорла", "зорлық", "ұрып", "соққыға",
    "суицид", "өзін-өзі өлтір",
    # en
    "died", "dies\\b", "death", "dead\\b", "deceased", "passed away", "killed", "kill\\b", "murder", "funeral",
    "rape", "raped", "abuse", "abusive", "assault", "beaten", "beats me", "violen", "suicide",
)

UNPROMPTED: tuple[str, ...] = (
    # ru
    "инвалид", "болезн", "болен", "больн", "больнич", "онколог", "диагноз", "беремен",
    "развод", "развест", "бывш", "опек", "отобрал", "забрал ребён", "забрали ребён",
    "краж", "украл", "ограбил", "мошенн", "преступ", "потерял работу", "нечем платить", "кормил",
    # kk
    "мүгедек", "ауру", "ауырып", "ажырас", "бұрынғы", "ұрла", "алаяқ", "қылмыс", "жұмыссыз", "асыраушы",
    # en
    "disab", "illness", "sick", "cancer", "pregnan", "divorce", "ex-", "my ex\\b", "custody", "stolen", "theft",
    "scam", "fraud", "crime", "lost my job", "breadwinner",
)

# Taxonomy branches (country-neutral ids of the global catalogue) never offered unprompted.
SENSITIVE_BRANCHES: frozenset[str] = frozenset({"inheritance", "family", "criminal"})
UNPROMPTED_OK: frozenset[str] = frozenset({"family.alimony"})


def _compile(stems: tuple[str, ...]) -> re.Pattern[str]:
    return re.compile(r"\b(?:" + "|".join(s if "\\" in s else re.escape(s) for s in stems) + ")", re.IGNORECASE)


_ALWAYS = _compile(ALWAYS)
_UNPROMPTED = _compile(UNPROMPTED + ALWAYS)


# The default set is short, tidy sentences: long stories and deliberately informal classifier samples
# (lower-case slang such as «бабки не возвращают») stay for the classifier and for chosen topics.
MAX_UNPROMPTED_LEN = 60


def allowed(text: str, *, prompted: bool) -> bool:
    """May ``text`` be offered as a suggestion? ``prompted`` — the person chose a topic themselves."""
    if prompted:
        return not _ALWAYS.search(text)
    return (len(text) <= MAX_UNPROMPTED_LEN and text[:1].isupper() and not _UNPROMPTED.search(text))


def sensitive_area(taxonomy_id: str | None) -> bool:
    """A taxonomy area (dispute id or prefix) kept out of the default (unprompted) suggestions."""
    if not taxonomy_id:
        return False
    parts = taxonomy_id.split(".")
    if len(parts) > 2:  # local additions look like "<cc>.<branch>.<dispute>"
        parts = parts[1:]
    return parts[0] in SENSITIVE_BRANCHES and ".".join(parts[:2]) not in UNPROMPTED_OK
