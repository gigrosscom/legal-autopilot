"""Create skeleton jurisdiction packs for CIS and MENA countries (status: planned).

Planned packs carry only facts that need no legal review (country name, currency, time zone, languages the
product supports) and the compliance texts. They have NO scenarios, forums, norms, deadlines, fees or emergency
numbers: those are added by lawyers of each country through REVIEW.md. Until then the country is shown as
"soon" with a waitlist and no cases are accepted.

    python scripts/build_planned_packs.py
"""

from __future__ import annotations

from pathlib import Path

import yaml

PACKS = Path(__file__).resolve().parents[1] / "packs"

# country: (names, currency, time zone, pack languages)
COUNTRIES = {
    "UZ": ({"ru": "Узбекистан", "kk": "Өзбекстан", "en": "Uzbekistan", "ar": "أوزبكستان", "tr": "Özbekistan"},
           "UZS", "Asia/Tashkent", ["ru", "en"]),
    "KG": ({"ru": "Кыргызстан", "kk": "Қырғызстан", "en": "Kyrgyzstan", "ar": "قيرغيزستان", "tr": "Kırgızistan"},
           "KGS", "Asia/Bishkek", ["ru", "en"]),
    "TJ": ({"ru": "Таджикистан", "kk": "Тәжікстан", "en": "Tajikistan", "ar": "طاجيكستان", "tr": "Tacikistan"},
           "TJS", "Asia/Dushanbe", ["ru", "en"]),
    "AZ": ({"ru": "Азербайджан", "kk": "Әзірбайжан", "en": "Azerbaijan", "ar": "أذربيجان", "tr": "Azerbaycan"},
           "AZN", "Asia/Baku", ["ru", "en", "tr"]),
    "AM": ({"ru": "Армения", "kk": "Армения", "en": "Armenia", "ar": "أرمينيا", "tr": "Ermenistan"},
           "AMD", "Asia/Yerevan", ["ru", "en"]),
    "GE": ({"ru": "Грузия", "kk": "Грузия", "en": "Georgia", "ar": "جورجيا", "tr": "Gürcistan"},
           "GEL", "Asia/Tbilisi", ["ru", "en"]),
    "TR": ({"ru": "Турция", "kk": "Түркия", "en": "Türkiye", "ar": "تركيا", "tr": "Türkiye"},
           "TRY", "Europe/Istanbul", ["tr", "en"]),
    "AE": ({"ru": "ОАЭ", "kk": "БАӘ", "en": "United Arab Emirates", "ar": "الإمارات العربية المتحدة",
            "tr": "Birleşik Arap Emirlikleri"}, "AED", "Asia/Dubai", ["ar", "en"]),
    "SA": ({"ru": "Саудовская Аравия", "kk": "Сауд Арабиясы", "en": "Saudi Arabia", "ar": "المملكة العربية السعودية",
            "tr": "Suudi Arabistan"}, "SAR", "Asia/Riyadh", ["ar", "en"]),
    "QA": ({"ru": "Катар", "kk": "Катар", "en": "Qatar", "ar": "قطر", "tr": "Katar"}, "QAR", "Asia/Qatar", ["ar", "en"]),
    "EG": ({"ru": "Египет", "kk": "Мысыр", "en": "Egypt", "ar": "مصر", "tr": "Mısır"}, "EGP", "Africa/Cairo", ["ar", "en"]),
    "JO": ({"ru": "Иордания", "kk": "Иордания", "en": "Jordan", "ar": "الأردن", "tr": "Ürdün"}, "JOD", "Asia/Amman",
           ["ar", "en"]),
    "MA": ({"ru": "Марокко", "kk": "Марокко", "en": "Morocco", "ar": "المغرب", "tr": "Fas"}, "MAD", "Africa/Casablanca",
           ["ar", "en"]),
}

COMPLIANCE = {
    "ai_label": {
        "ru": "Подготовлено с помощью ИИ (Konsiliér AI). Проверьте данные перед подачей.",
        "en": "Prepared with AI (Konsiliér AI). Check the details before filing.",
        "ar": "أُعدّ بمساعدة الذكاء الاصطناعي (Konsiliér AI). تحقّق من البيانات قبل التقديم.",
        "tr": "Yapay zekâ ile hazırlandı (Konsiliér AI). Başvurmadan önce bilgileri kontrol edin.",
    },
    "draft_disclaimer": {
        "ru": "ЧЕРНОВИК: сценарий ещё не подписан юристом. Ссылки на нормы и сроки подлежат проверке.",
        "en": "DRAFT: this scenario has not yet been signed off by a lawyer. Legal references and deadlines must be checked.",
        "ar": "مسودة: لم يعتمد محامٍ هذا السيناريو بعد. يجب التحقق من الإحالات إلى النصوص القانونية والمواعيد.",
        "tr": "TASLAK: Senaryo henüz bir avukat tarafından onaylanmadı. Mevzuat ve süre atıfları kontrol edilmelidir.",
    },
    "service_disclaimer": {
        "ru": "Konsiliér AI помогает подготовить и подать документы и следит за сроками. Если нужно довести дело "
              "до результата — подключим профессионального юриста платформы. Документы подаются от вашего имени.",
        "en": "Konsiliér AI helps you prepare and file documents and keeps track of deadlines. If your case needs to "
              "be seen through to the end, we will bring in a professional lawyer from the platform. "
              "Documents are filed in your name.",
        "ar": "يساعدك Konsiliér AI على إعداد المستندات وتقديمها ويتابع المواعيد. وإذا لزم إيصال القضية إلى "
              "نتيجة، نُشرك محاميًا محترفًا من المنصة. تُقدَّم المستندات باسمك.",
        "tr": "Konsiliér AI belgeleri hazırlamanıza ve sunmanıza yardım eder, süreleri takip eder. Dosyanın sonuca "
              "ulaştırılması gerekirse platformdaki profesyonel bir avukatı dahil ederiz. Belgeler sizin adınıza sunulur.",
    },
}

REVIEW = """# {cc} — статус пакета: planned

Пакет создан как каркас (scripts/build_planned_packs.py). В нём нет норм, органов, сроков, пошлин,
экстренных номеров и сценариев. Страна показывается на /coverage как «скоро», дела не принимаются.

Чтобы запустить страну, юрист страны заполняет и подписывает:

- [ ] `routing.yaml`: экстренные номера (с источником), правила о юридической практике без лицензии,
      норма об ответственности за ложный донос, порог суммы для передачи юристу;
- [ ] `forums/*.yaml`: реестр органов (подсудность, способы подачи, сроки ответа, пошлины, эскалация,
      правовой эффект) — только государственные и признанные государством органы;
- [ ] `documents/*.yaml` и шаблоны `templates/generic/*.docx` с обязательными реквизитами страны;
- [ ] `i18n/<lang>.yaml`: вопросы интервью и тексты на языках страны;
- [ ] после проверки: `status: live` в `pack.yaml`.
"""


def main() -> None:
    for cc, (names, currency, tz, langs) in COUNTRIES.items():
        root = PACKS / cc.lower()
        root.mkdir(parents=True, exist_ok=True)
        pack_yaml = root / "pack.yaml"
        old = yaml.safe_load(pack_yaml.read_text("utf-8")) if pack_yaml.is_file() else {}
        manifest = {
            "country": cc, "name": names, "currency": currency, "timezone": tz, "languages": langs,
            "default_language": langs[0], "status": "planned",
            "compliance": {k: {lang: v[lang] for lang in langs} for k, v in COMPLIANCE.items()},
        }
        if old.get("legal_sources"):  # researched data (docs/legal-sources.md): keep across regenerations
            manifest["legal_sources"] = old["legal_sources"]
        header = ("# Skeleton pack (status: planned). No legal data until reviewed by a lawyer of the country.\n"
                  "# Generated by scripts/build_planned_packs.py.\n")
        (root / "pack.yaml").write_text(header + yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False),
                                        "utf-8")
        review = root / "REVIEW.md"
        if not review.exists():
            review.write_text(REVIEW.format(cc=cc), "utf-8")
        print("wrote", root)


if __name__ == "__main__":
    main()
