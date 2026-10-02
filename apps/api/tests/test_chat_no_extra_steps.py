from konsilier.chat import drop_extra_steps


def test_flood_steps_without_appraiser():
    text = ("Что делать:\n1. Составьте акт о затоплении в КСК.\n2. Оцените ущерб. Пригласите оценщика или подготовьте "
            "смету.\n3. Направьте претензию соседу.\n4. Обратитесь в суд.\n[[MORE]]\nПодробнее: суд может назначить "
            "экспертизу, если сосед оспорит сумму.")
    out = drop_extra_steps(text)
    assert "оценщик" not in out
    assert "1. Составьте акт" in out and "2. Направьте претензию" in out and "3. Обратитесь в суд" in out
    assert "суд может назначить экспертизу" in out


def test_notary_line_dropped():
    out = drop_extra_steps("Что делать:\n1. Заверьте переписку.\n2. Обратитесь к нотариусу для заверения.\n3. Подайте жалобу.")
    assert "нотариус" not in out and "2. Подайте жалобу" in out


def test_clean_reply_unchanged():
    text = "Что делать:\n1. Направьте претензию продавцу.\n2. Если откажет — в суд."
    assert drop_extra_steps(text) == text
