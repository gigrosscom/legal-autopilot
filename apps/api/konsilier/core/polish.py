"""Tidy text of a document (owner 01.10, the first paid claim): names and addresses typed in lower case, gendered
forms left in brackets, amounts in figures and words. Language rules only — nothing here knows the country."""
from __future__ import annotations

import re

# ---------------------------------------------------------------- names and addresses
_FORMS = {"тоо": "ТОО", "ип": "ИП", "ао": "АО", "оао": "ОАО", "зао": "ЗАО", "ооо": "ООО", "кх": "КХ", "чп": "ЧП",
          "llp": "LLP", "llc": "LLC", "ltd": "Ltd", "inc": "Inc", "жшс": "ЖШС", "ак": "АҚ"}
_MARKS = {"г": "г.", "город": "г.", "ул": "ул.", "улица": "ул.", "пр": "пр.", "пр-т": "пр.", "проспект": "пр.",
          "мкр": "мкр", "микрорайон": "мкр", "д": "д.", "дом": "д.", "кв": "кв.", "квартира": "кв.", "б-р": "б-р",
          "бульвар": "б-р", "пер": "пер.", "переулок": "пер.", "ш": "ш.", "шоссе": "ш.", "р-н": "р-н", "район": "р-н",
          "обл": "обл.", "область": "обл.", "пос": "пос.", "поселок": "пос.", "посёлок": "пос.", "с": "с.", "село": "с.",
          "оф": "оф.", "офис": "оф.", "корп": "корп.", "корпус": "корп.", "блок": "блок", "нп": "НП", "вп": "ВП"}
_STREET = {"ул.", "пр.", "мкр", "б-р", "пер.", "ш."}


def _cap(word: str) -> str:
    return "-".join(p[:1].upper() + p[1:] for p in word.split("-"))


def tidy_name(value: str | None) -> str:
    """«антропик» → «Антропик», «тоо ромашка» → «ТОО Ромашка»: only when typed all in lower case — a name written
    by the person with capitals stays exactly as written."""
    s = (value or "").strip()
    if not s or any(ch.isupper() for ch in s):
        return s[:1].upper() + s[1:] if s else s
    return " ".join(_FORMS.get(w, w if not w[:1].isalpha() else _cap(w)) for w in s.split())


def tidy_address(value: str | None) -> str:
    """«алматы сейдимбек 222» → «Алматы, ул. Сейдимбек, 222». Only an address typed all in lower case is rebuilt
    (city, street, numbers); one with capitals stays as written."""
    s = (value or "").strip()
    if not s or any(ch.isupper() for ch in s):
        return s
    if "," in s:  # the person split it already: capitals only
        return ", ".join(" ".join(_MARKS.get(w.rstrip("."), _cap(w) if w[:1].isalpha() else w) for w in part.split())
                         for part in s.split(","))
    words = s.replace(".", ". ").split()
    out: list[str] = []
    street_seen = any(_MARKS.get(w.rstrip(".")) in _STREET for w in words)
    city_done = False
    i = 0
    while i < len(words):
        w = words[i].rstrip(".")
        mark = _MARKS.get(w)
        if mark:
            out.append((", " if out else "") + mark)
            i += 1
            nxt = words[i].rstrip(".") if i < len(words) else ""
            if nxt and (nxt[:1].isalpha() or mark not in _STREET | {"г."}):  # «ул. Абая», «кв. 5», «д. 3»
                out[-1] += " " + (_cap(nxt) if nxt[:1].isalpha() else nxt)
                city_done = city_done or mark == "г."
                i += 1
            continue
        if w[:1].isalpha():
            if not out:
                out.append(_cap(w))
                city_done = True
            elif city_done and not street_seen:
                out.append(", ул. " + _cap(w))
                street_seen = True
            elif out[-1][-1:].isalpha():
                out[-1] += " " + _cap(w)
            else:
                out.append(", " + _cap(w))
        else:
            out.append(", " + w)
        i += 1
    return "".join(out).lstrip(", ")


# ---------------------------------------------------------------- grammatical gender
def gender_from_name(full_name: str | None) -> str:
    """From the patronymic, else the surname ending; 'unknown' when neither tells."""
    words = [w.lower().strip(".,") for w in (full_name or "").split()]
    for w in words:
        if w.endswith(("вич", "ұлы", "улы", "оглы", "uly")):
            return "male"
        if w.endswith(("вна", "чна", "қызы", "кызы", "кизи", "qyzy")):
            return "female"
    if words:
        last = words[0]
        if last.endswith(("ова", "ева", "ёва", "ина", "ына", "ская", "цкая")):
            return "female"
        if last.endswith(("ов", "ев", "ёв", "ин", "ын", "ский", "цкий")):
            return "male"
    return "unknown"


def gender_from_id(number: str | None, position: int | None, male: str, female: str) -> str:
    """A national id number whose digit at `position` (1-based) tells the sex (the pack says which digits)."""
    digits = re.sub(r"\D", "", number or "")
    if not position or len(digits) < position:
        return "unknown"
    d = digits[position - 1]
    return "male" if d in male else "female" if d in female else "unknown"


_REFLEXIVE = re.compile(r"(\w+?)ся\s?\(ась\)")
_SUFFIX = re.compile(r"(\w+)\s?\(а\)")


def gender_forms(text: str, gender: str) -> str:
    """«приобрел(а)» → «приобрёл» / «приобрела»; «обратился(ась)» → «обратился» / «обратилась». Unknown: as is."""
    if gender not in ("male", "female") or "(" not in text:
        return text
    if gender == "male":
        return _SUFFIX.sub(r"\1", _REFLEXIVE.sub(r"\1ся", text))
    return _SUFFIX.sub(r"\1а", _REFLEXIVE.sub(r"\1ась", text))


# ---------------------------------------------------------------- amounts in words
_RU_UNITS = ["", "один", "два", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять", "десять", "одиннадцать",
             "двенадцать", "тринадцать", "четырнадцать", "пятнадцать", "шестнадцать", "семнадцать", "восемнадцать",
             "девятнадцать"]
_RU_TENS = ["", "", "двадцать", "тридцать", "сорок", "пятьдесят", "шестьдесят", "семьдесят", "восемьдесят", "девяносто"]
_RU_HUNDREDS = ["", "сто", "двести", "триста", "четыреста", "пятьсот", "шестьсот", "семьсот", "восемьсот", "девятьсот"]
_RU_SCALES = [(("", "", ""), False), (("тысяча", "тысячи", "тысяч"), True), (("миллион", "миллиона", "миллионов"), False),
              (("миллиард", "миллиарда", "миллиардов"), False)]

_KK_UNITS = ["", "бір", "екі", "үш", "төрт", "бес", "алты", "жеті", "сегіз", "тоғыз"]
_KK_TENS = ["", "он", "жиырма", "отыз", "қырық", "елу", "алпыс", "жетпіс", "сексен", "тоқсан"]
_KK_SCALES = ["", "мың", "миллион", "миллиард"]


def _ru_triplet(n: int, feminine: bool) -> list[str]:
    out = [_RU_HUNDREDS[n // 100]]
    rest = n % 100
    if rest < 20:
        unit = _RU_UNITS[rest]
    else:
        out.append(_RU_TENS[rest // 10])
        unit = _RU_UNITS[rest % 10]
    if feminine and unit in ("один", "два"):
        unit = {"один": "одна", "два": "две"}[unit]
    out.append(unit)
    return [w for w in out if w]


def _ru_plural(n: int, forms: tuple[str, str, str]) -> str:
    n %= 100
    if 11 <= n <= 19:
        return forms[2]
    return forms[0] if n % 10 == 1 else forms[1] if n % 10 in (2, 3, 4) else forms[2]


def number_words(n: int, lang: str) -> str | None:
    """A whole amount in words (ru, kk); None for another language or a number out of range."""
    if n < 0 or n >= 10 ** 12:
        return None
    if n == 0:
        return {"ru": "ноль", "kk": "нөл"}.get(lang)
    groups = []
    while n:
        groups.append(n % 1000)
        n //= 1000
    words: list[str] = []
    if lang == "ru":
        for i in range(len(groups) - 1, -1, -1):
            g = groups[i]
            if not g:
                continue
            forms, feminine = _RU_SCALES[i]
            words += _ru_triplet(g, feminine)
            if i:
                words.append(_ru_plural(g, forms))
        return " ".join(words)
    if lang == "kk":
        for i in range(len(groups) - 1, -1, -1):
            g = groups[i]
            if not g:
                continue
            h, t, u = g // 100, g % 100 // 10, g % 10
            if h:
                words += ([_KK_UNITS[h]] if h > 1 else []) + ["жүз"]
            words += [w for w in (_KK_TENS[t], _KK_UNITS[u]) if w]
            if i:
                words.append(_KK_SCALES[i])
        return " ".join(words)
    return None


def amounts_in_words(text: str, code: str, symbol: str, word: str, lang: str) -> str:
    """«10 352 <code>» → «10 352 <sign> (десять тысяч триста пятьдесят два <word>)» for every whole amount followed by the
    currency code; an amount with kopecks keeps its figures only."""
    if code not in text:
        return text

    def repl(m: re.Match[str]) -> str:
        figures = m.group(1)
        number = re.sub(r"\D", "", figures)
        spelled = number_words(int(number), lang) if number and not m.group(2) else None
        shown = f"{figures}{m.group(2) or ''} {symbol or code}"
        return f"{shown} ({spelled} {word})" if spelled and word else shown
    return re.sub(rf"(\d{{1,3}}(?:[ \u00a0\u202f]\d{{3}})*|\d+)([.,]\d{{1,2}})?\s{re.escape(code)}\b", repl, text)
