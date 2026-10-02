"""Owner 02.10 / ZANN: a term of days or an article number reaches the person only if it is checked — in the country
rules (checked on adilet) or in an article opened in this reply. Cases are the real errors of the QA runs 02.10."""

from __future__ import annotations

from pathlib import Path

from konsilier.chat import checked_terms, keep_checked
from konsilier.core.packs import PackRegistry

RULES = PackRegistry.load(Path(__file__).parents[3] / "packs").pack("KZ").manifest.chat_rules


def test_checked_list_from_the_rules():
    days, arts = checked_terms(RULES)
    assert {(5, "working"), (10, "calendar"), (14, "calendar"), (20, "calendar"), (15, "working")} <= days
    assert (30, "") not in days and (3, "") not in days and (7, "") not in days  # quoted wrong examples
    assert {"42-4", "29-1", "842", "159", "64", "82"} <= arts


def test_motor_insurer_ten_working_days_taken_out():
    text = ("Что делать:\n1. **Подайте заявление** в страховую.\n2. **Обратитесь в суд**, если страховая не ответит "
            "в течение 10 рабочих дней.")
    out, removed = keep_checked(text, RULES, set())
    assert "10 рабочих" not in out and "2. **Обратитесь в суд**, если страховая не ответит." in out
    assert removed == ["в течение 10 рабочих дней"]


def test_wrong_sentence_in_details_taken_out_right_one_kept():
    text = ("[[MORE]]\nСрок ремонта не должен превышать 15 календарных дней. Продавец отвечает на претензию в течение "
            "10 календарных дней.")
    out, _ = keep_checked(text, RULES, set())
    assert "15 календарных" not in out and "в течение 10 календарных дней" in out


def test_unchecked_article_number_becomes_a_norm():
    out, removed = keep_checked("Согласно статье 157 Трудового кодекса вы можете приостановить работу.", RULES, set())
    assert out.startswith("Согласно норме Трудового кодекса") and removed
    out, _ = keep_checked("Пеня положена (ст. 113 ТК), а штрафы запрещены (ст. 999 ТК).", RULES, set())
    assert "ст. 113" in out and "999" not in out


def test_opened_article_and_its_terms_pass():
    text = "По статье 999 срок — 7 рабочих дней."
    out, removed = keep_checked(text, RULES, {"999"}, opened_any=True)
    assert out == text and not removed


def test_clean_reply_unchanged():
    text = "Что делать:\n1. **Направьте претензию продавцу.** Ответ — в течение 10 календарных дней."
    assert keep_checked(text, RULES, set()) == (text, [])


def test_unchecked_article_in_brackets_goes_whole():
    out, removed = keep_checked("Увольнение на больничном запрещено (статья 999 Трудового кодекса). Дальше.", RULES, set())
    assert out == "Увольнение на больничном запрещено. Дальше." and removed == ["(статья 999 Трудового кодекса)"]
    text = "Претензия — ответ 10 календарных дней (ст. 42-4 ЗоЗПП)."
    assert keep_checked(text, RULES, set()) == (text, [])


def test_months_checked_only_as_a_time_limit():
    """ТК ст. 160 (with КС 81-НП, 88-НП): 1 and 2 months, 1 and 3 years are checked; «6 месяцев» is not."""
    out, removed = keep_checked("В суд можно обратиться в течение шести месяцев.", RULES, set())
    assert "шести месяцев" not in out and removed
    text = "В суд — в течение двух месяцев со дня получения решения комиссии."
    assert keep_checked(text, RULES, set()) == (text, [])
    text = "Ноутбук держат уже пять месяцев, это нарушение."  # the person's fact, not a time limit
    assert keep_checked(text, RULES, set()) == (text, [])
