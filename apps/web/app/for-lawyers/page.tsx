"use client";

import { useEffect, useMemo, useState } from "react";
import { publicApi, errorText } from "@/lib/api";
import { useLang } from "@/lib/i18n";

// NOTE: commercial terms below are the proposed model (see docs/BUSINESS_MODEL.md) — edit them here, in both languages.
// Kazakh copy is kept short so it fits on narrow phones.
const TEXT = {
  ru: {
    proPrice: "15 000–25 000 ₸/мес",
    pains: [
      ["Клиенты приходят с «меня обманули» и пакетом скриншотов", "Вы получаете готовое досье: факты, даты, суммы, доказательства, переписка и хронология — ИИ собрал и проверил их до вас."],
      ["Реклама дорогая, сарафан непредсказуем", "Дела по вашей специализации и городу приходят сами. Вы выбираете, на какие откликнуться, и называете свою цену."],
      ["Клиент пропал после первого этапа и не заплатил", "Оплата по этапам через резерв: клиент вносит сумму заранее, вы получаете её сразу после выполнения этапа."],
    ],
    benefits: [
      ["📂", "Готовые дела", "Досье вместо первичной консультации — экономия 1–2 часов на каждом клиенте.", false],
      ["💰", "0% с вашего гонорара", "Ваша цена — ваши деньги. Сервисный сбор платит клиент за безопасную сделку.", false],
      ["🔒", "Гарантия оплаты", "Деньги клиента в резерве до выполнения этапа. Никаких «переведу завтра».", true],
      ["🤖", "ИИ-помощник", "Черновики исков и жалоб, резюме дела, контроль процессуальных сроков с напоминаниями.", false],
      ["🏆", "Репутация, которую нельзя купить", "Рейтинг по доказанным результатам: выигранные дела и возвращённые деньги, а не отзывы друзей.", false],
      ["👥", "Ваши клиенты — ваши", "Ведите на платформе и своих клиентов: CRM, сроки, документы. Без комиссии для приведённых вами.", false],
    ] as [string, string, string, boolean][],
    faq: [
      ["Сколько платформа берёт с юриста?", "С гонорара — 0%. Базовый тариф бесплатный. Pro (без лимита откликов, приоритет, ИИ-инструменты, CRM) — 15 000–25 000 ₸/мес. Партнёрам Konsilier.AI — Pro бесплатно 6 месяцев, экспертам сценариев — 12 месяцев."],
      ["Кто может присоединиться?", "Адвокаты, юридические консультанты — члены палаты, правозащитные организации. Статус проверяем по реестрам, личность — через ЭЦП."],
      ["А адвокатская тайна и этика?", "Персональные данные клиента скрыты до заключения договора: вы видите обезличенную карточку дела. Договор заключаете вы с клиентом напрямую, платформа — технологический посредник."],
      ["Правозащитникам тоже платить?", "Нет. Для НКО и pro bono — бесплатно навсегда, с отчётами о помощи для доноров и грантодателей."],
    ],
    calc: {
      title: "Посчитайте для себя",
      cases: "Новых дел в месяц через платформу",
      fee: "Средний гонорар за дело",
      income: "дополнительный доход в месяц, без комиссии с гонорара",
      hoursUnit: "ч",
      hours: "сэкономлено на первичном разборе (≈1,5 ч на дело)",
      note: "Иллюстративный расчёт по вашим вводным, не обещание дохода.",
    },
    dossier: {
      chip: "Новое дело · Защита прав потребителей",
      example: "пример",
      title: "Возврат 180 000 ₸ за недоставленный диван (маркетплейс)",
      rows: [["Город", "Алматы"], ["Сумма требований", "180 000 ₸"], ["Дата оплаты", "15.08.2026"], ["Доказательства", "чек, скриншот заказа, переписка"], ["Уже сделано", "претензия продавцу подана 01.09"], ["Ответ продавца", "отказ (срок истёк)"]],
      hidden: "ФИО и контакты клиента откроются после заключения договора.",
      respond: "Откликнуться: моя цена",
      ask: "Задать вопрос клиенту",
    },
    card: {
      sample: "пример карточки",
      partner: "партнёр платформы",
      spec: "Защита прав потребителей · Алматы",
      score: "рейтинг по доказанным результатам",
      cases: "дела",
      recovered: "возвращено",
      mln: "млн",
      pending: "⭐ Партнёр Konsilier.AI. Рейтинг по доказанным результатам появится после первых завершённых дел.",
      footer: "konsilier.com · запись к юристу",
    },
    form: {
      title: "Стать партнёром Konsilier.AI",
      invited: "Вас пригласил коллега · +3 месяца Pro",
      name: "ФИО",
      kinds: [["advocate", "Адвокат"], ["legal_consultant", "Юридический консультант"], ["human_rights", "Правозащитная организация / НКО"], ["other", "Другое"]],
      org: "Коллегия / палата / организация",
      license: "Номер лицензии / удостоверения",
      city: "Город",
      contact: "Телефон, Telegram или e-mail",
      specs: [["consumer", "Защита прав потребителей"], ["credit_fraud", "Мошеннические кредиты"], ["debt_collectors", "Коллекторы и долги"], ["labor", "Трудовые споры"], ["family", "Семейные дела"], ["business", "Бизнес и дебиторка"]],
      expert: "Хочу быть экспертом сценариев — проверять нормы, сроки и шаблоны по своей специализации (Pro 12 месяцев)",
      message: "Что для вас важно в платформе? (необязательно)",
      busy: "Отправляем…",
      submit: "Подать заявку",
      privacy: "Проверяем статус по реестрам. Данные используем только для проверки и связи с вами.",
      doneTitle: "Заявка принята 🎉",
      doneText: "Мы проверим статус и свяжемся с вами. Пока — ваша личная ссылка. Каждый коллега, который присоединится по ней, даёт вам и ему +3 месяца Pro, а первые 10 приглашённых поднимают вас в ранней выдаче дел.",
      copy: "Копировать",
      share: "Присоединяюсь к Konsilier.AI — платформе, где юристы получают готовые дела с досье, 0% комиссии с гонорара и оплату по этапам. Программа «Партнёр Konsilier.AI»: Pro бесплатно 6 месяцев. ",
    },
    hero: {
      chip: "Для адвокатов, юристов и правозащитников",
      title: "Клиенты приходят к вам с готовым делом. Вы занимаетесь правом — а не поиском клиентов и бумагами.",
      sub: "ИИ собирает факты и доказательства, платформа гарантирует оплату по этапам, а ваш рейтинг строится на реальных выигранных делах. 0% с вашего гонорара.",
      apply: "Стать партнёром — бесплатно",
      rating: "Как выглядит рейтинг",
      perks: "Партнёрам — Pro бесплатно 6 месяцев, экспертам сценариев — 12 месяцев.",
    },
    painsTitle: "Знакомо?",
    benefitsTitle: "Что вы получаете",
    soon: "скоро",
    reputationTitle: "Ваша репутация — ваш актив",
    reputation: "Карточка с рейтингом по доказанным результатам — ваша цифровая визитка. Делитесь ей в Instagram, Telegram и LinkedIn: клиенты записываются к вам напрямую, без комиссии.",
    growthTitle: "Растите вместе с платформой",
    growth: [
      ["🤝", "Пригласите коллегу", "+3 месяца Pro вам и ему. 10 приглашённых — приоритет в выдаче дел."],
      ["📣", "Кейс недели", "ИИ готовит обезличенный пост о вашем выигранном деле — публикуйте в один клик."],
      ["🏅", "Топ месяца", "Лидеры по возвратам в каждой категории и городе — на главной и в наших соцсетях."],
      ["🧾", "Свои клиенты — без комиссии", "Приглашайте своих клиентов по личной ссылке: CRM, сроки и документы бесплатно."],
    ],
    partner: {
      title: "Программа «Партнёр Konsilier.AI»",
      intro: "Первые 100 проверенных юристов, адвокатов и правозащитников, которые вместе с нами проводят пилот платформы. Статус — не за регистрацию, а за участие.",
      doesTitle: "Что делает партнёр",
      does: ["Проходит проверку статуса и личности.", "Берёт в работу 3–5 дел с платформы в месяц.", "Соблюдает стандарты: прозрачная цена до начала работы, сроки этапов, отметки о ходе дела в карточке.", "Раз в месяц даёт обратную связь по документам и сценариям — что исправить, чего не хватает."],
      getsTitle: "Что получает партнёр",
      gets: ["Pro бесплатно на 6 месяцев.", "Статус «Партнёр» в профиле и карточке.", "Приоритет в выдаче дел в пилотный период.", "Влияние на продукт: сценарии и шаблоны строятся с учётом практики партнёров."],
      lose: "Если условия участия не выполняются, статус снимается, аккаунт остаётся на базовом тарифе.",
    },
    expert: {
      title: "Эксперт сценариев",
      chip: "Pro бесплатно 12 месяцев",
      intro: "Юристы, которые отвечают за правовую точность платформы. Каждый сценарий (например, «возврат денег за товар») — это готовая последовательность документов, сроков и адресатов. Эксперт проверяет его и подписывает своим именем.",
      doesTitle: "Что делает эксперт",
      does: ["Проверяет нормы, сроки и адресатов в сценарии своей специализации.", "Проверяет шаблоны документов (претензии, жалобы, заявления).", "Обновляет сценарий при изменении законодательства.", "Разбирает спорные случаи по методологии."],
      getsTitle: "Что получает эксперт",
      gets: ["Pro бесплатно на 12 месяцев.", "Статус «Эксперт» и имя в каждом проверенном сценарии: «Сценарий проверен: …».", "Первым получает дела по своим сценариям.", "Упоминание в материалах и соцсетях Konsilier.AI."],
    },
    pricing: {
      title: "Тарифы",
      basic: "Базовый",
      basicText: "Профиль, проверка статуса, отклики на дела (лимит в месяц), рейтинг.",
      proChip: "Партнёрам 6 мес., экспертам 12 мес. бесплатно",
      proText: "Без лимита откликов, приоритет в выдаче, ИИ-черновики, контроль сроков, CRM своих клиентов.",
      ngo: "Правозащитникам и НКО",
      ngoPrice: "0 ₸ навсегда",
      ngoText: "Pro-функции для pro bono и отчёты о помощи для доноров.",
    },
    faqTitle: "Вопросы",
  },
  kk: {
    proPrice: "15 000–25 000 ₸/ай",
    pains: [
      ["Клиент «алданып қалдым» деп, бір топ скриншотпен келеді", "Сізге дайын досье келеді: деректер, күндер, сомалар, дәлелдер, хат алмасу және хронология — ЖИ бәрін алдын ала жинап, тексерген."],
      ["Жарнама қымбат, таныстар арқылы клиент тұрақсыз", "Мамандығыңыз бен қалаңыз бойынша істер өзі келеді. Қайсысына жауап беретініңізді өзіңіз таңдап, бағаңызды айтасыз."],
      ["Клиент бірінші кезеңнен кейін жоғалып, төлемеді", "Кезеңмен төлеу резерв арқылы: клиент ақшаны алдын ала салады, кезең орындалған соң бірден аласыз."],
    ],
    benefits: [
      ["📂", "Дайын істер", "Алғашқы кеңес орнына досье — әр клиентте 1–2 сағат үнем.", false],
      ["💰", "Гонорардан 0%", "Бағаңыз — өз ақшаңыз. Қауіпсіз мәміле үшін сервистік алымды клиент төлейді.", false],
      ["🔒", "Төлем кепілдігі", "Клиенттің ақшасы кезең орындалғанша резервте. «Ертең аударамын» жоқ.", true],
      ["🤖", "ЖИ-көмекші", "Талап пен шағым жобалары, іс түйіндемесі, іс жүргізу мерзімдерін еске салу.", false],
      ["🏆", "Сатып алуға болмайтын бедел", "Дәлелденген нәтиже бойынша рейтинг: жеңген іс пен қайтарылған ақша, достардың пікірі емес.", false],
      ["👥", "Өз клиенттеріңіз — сіздікі", "Өз клиенттеріңізді де платформада жүргізіңіз: CRM, мерзімдер, құжаттар. Өзіңіз әкелгенге комиссия жоқ.", false],
    ] as [string, string, string, boolean][],
    faq: [
      ["Платформа заңгерден қанша алады?", "Гонорардан — 0%. Базалық тариф тегін. Pro (жауап лимитсіз, басымдық, ЖИ-құралдар, CRM) — 15 000–25 000 ₸/ай. Konsilier.AI серіктестеріне Pro 6 ай тегін, сценарий сарапшыларына — 12 ай."],
      ["Кім қосыла алады?", "Адвокаттар, палата мүшесі заң кеңесшілері, құқық қорғау ұйымдары. Мәртебе тізілімдер бойынша, жеке басы ЭЦҚ арқылы тексеріледі."],
      ["Адвокаттық құпия мен этика ше?", "Шарт жасалғанша клиенттің жеке деректері жасырын: сіз иесіз іс карточкасын көресіз. Шартты клиентпен тікелей өзіңіз жасайсыз, платформа — технологиялық делдал."],
      ["Құқық қорғаушылар да төлей ме?", "Жоқ. ҮЕҰ мен pro bono үшін — мәңгі тегін, донорларға көмек туралы есептермен."],
    ],
    calc: {
      title: "Өзіңіз есептеңіз",
      cases: "Айына платформадан жаңа іс",
      fee: "Бір істің орташа гонорары",
      income: "айына қосымша табыс, гонорардан комиссиясыз",
      hoursUnit: "сағ",
      hours: "алғашқы талдауда үнемделді (бір іске ≈1,5 сағ)",
      note: "Сіздің деректеріңіз бойынша үлгі есеп, табыс уәдесі емес.",
    },
    dossier: {
      chip: "Жаңа іс · Тұтынушы құқығы",
      example: "үлгі",
      title: "Жеткізілмеген диван үшін 180 000 ₸ қайтару (маркетплейс)",
      rows: [["Қала", "Алматы"], ["Талап сомасы", "180 000 ₸"], ["Төлем күні", "15.08.2026"], ["Дәлелдер", "чек, тапсырыс скриншоты, хат алмасу"], ["Не істелді", "сатушыға талап-арыз 01.09 берілді"], ["Сатушы жауабы", "бас тарту (мерзімі өтті)"]],
      hidden: "Клиенттің аты-жөні мен байланысы шарт жасалған соң ашылады.",
      respond: "Жауап беру: менің бағам",
      ask: "Клиентке сұрақ қою",
    },
    card: {
      sample: "карточка үлгісі",
      partner: "платформа серіктесі",
      spec: "Тұтынушы құқығы · Алматы",
      score: "дәлелденген нәтиже бойынша рейтинг",
      cases: "іс",
      recovered: "қайтарылды",
      mln: "млн",
      pending: "⭐ Konsilier.AI серіктесі. Рейтинг алғашқы істер аяқталған соң пайда болады.",
      footer: "konsilier.com · заңгерге жазылу",
    },
    form: {
      title: "Konsilier.AI серіктесі болу",
      invited: "Сізді әріптесіңіз шақырды · +3 ай Pro",
      name: "Аты-жөні",
      kinds: [["advocate", "Адвокат"], ["legal_consultant", "Заң кеңесшісі"], ["human_rights", "Құқық қорғау ұйымы / ҮЕҰ"], ["other", "Басқа"]],
      org: "Алқа / палата / ұйым",
      license: "Лицензия / куәлік нөмірі",
      city: "Қала",
      contact: "Телефон, Telegram не e-mail",
      specs: [["consumer", "Тұтынушы құқығы"], ["credit_fraud", "Алаяқтық несиелер"], ["debt_collectors", "Коллекторлар мен қарыз"], ["labor", "Еңбек даулары"], ["family", "Отбасы істері"], ["business", "Бизнес және дебиторлық қарыз"]],
      expert: "Сценарий сарапшысы болғым келеді — өз саламдағы нормаларды, мерзімдерді және үлгілерді тексеремін (Pro 12 ай)",
      message: "Платформада сізге не маңызды? (міндетті емес)",
      busy: "Жіберілуде…",
      submit: "Өтінім беру",
      privacy: "Мәртебені тізілімдер бойынша тексереміз. Деректерді тек тексеру және байланыс үшін қолданамыз.",
      doneTitle: "Өтінім қабылданды 🎉",
      doneText: "Мәртебеңізді тексеріп, хабарласамыз. Әзірге — жеке сілтемеңіз. Осы сілтеме арқылы қосылған әр әріптес сізге де, оған да +3 ай Pro береді, ал алғашқы 10 шақырылған сізді істер тізімінде жоғары көтереді.",
      copy: "Көшіру",
      share: "Konsilier.AI-ға қосылдым — заңгерлер досьесі бар дайын істер алатын, гонорардан 0% комиссия және кезеңмен төлем платформасы. «Konsilier.AI серіктесі» бағдарламасы: Pro 6 ай тегін. ",
    },
    hero: {
      chip: "Адвокаттарға, заңгерлерге, құқық қорғаушыларға",
      title: "Клиенттер сізге дайын іспен келеді. Сіз клиент іздеумен және қағазбен емес, құқықпен айналысасыз.",
      sub: "ЖИ деректер мен дәлелдерді жинайды, платформа кезеңмен төлемге кепілдік береді, рейтингіңіз нақты жеңген істерге негізделеді. Гонорардан 0%.",
      apply: "Серіктес болу — тегін",
      rating: "Рейтинг қалай көрінеді",
      perks: "Серіктестерге — Pro 6 ай тегін, сценарий сарапшыларына — 12 ай.",
    },
    painsTitle: "Таныс па?",
    benefitsTitle: "Не аласыз",
    soon: "жақында",
    reputationTitle: "Беделіңіз — активіңіз",
    reputation: "Дәлелденген нәтиже бойынша рейтингі бар карточка — сандық визиткаңыз. Instagram, Telegram және LinkedIn-де бөлісіңіз: клиенттер сізге тікелей, комиссиясыз жазылады.",
    growthTitle: "Платформамен бірге өсіңіз",
    growth: [
      ["🤝", "Әріптесті шақырыңыз", "Сізге де, оған да +3 ай Pro. 10 шақыру — істер тізімінде басымдық."],
      ["📣", "Апта кейсі", "ЖИ жеңген ісіңіз туралы иесіз пост дайындайды — бір басумен жариялаңыз."],
      ["🏅", "Ай үздігі", "Әр санат пен қаладағы қайтару көшбасшылары — басты бетте және әлеуметтік желілерімізде."],
      ["🧾", "Өз клиенттеріңіз — комиссиясыз", "Өз клиенттеріңізді жеке сілтемемен шақырыңыз: CRM, мерзімдер, құжаттар тегін."],
    ],
    partner: {
      title: "«Konsilier.AI серіктесі» бағдарламасы",
      intro: "Платформа пилотын бізбен бірге өткізетін алғашқы 100 тексерілген заңгер, адвокат және құқық қорғаушы. Мәртебе тіркелгені үшін емес, қатысқаны үшін беріледі.",
      doesTitle: "Серіктес не істейді",
      does: ["Мәртебе мен жеке басын тексеруден өтеді.", "Айына платформадан 3–5 іс алады.", "Стандарттарды сақтайды: жұмысқа дейін ашық баға, кезең мерзімдері, карточкада іс барысы.", "Айына бір рет құжаттар мен сценарийлер бойынша пікір береді — нені түзету, неге жетпейді."],
      getsTitle: "Серіктес не алады",
      gets: ["Pro 6 ай тегін.", "Профиль мен карточкада «Серіктес» мәртебесі.", "Пилот кезінде істер тізімінде басымдық.", "Өнімге ықпал: сценарийлер мен үлгілер серіктестердің тәжірибесімен жасалады."],
      lose: "Қатысу шарттары орындалмаса, мәртебе алынады, аккаунт базалық тарифте қалады.",
    },
    expert: {
      title: "Сценарий сарапшысы",
      chip: "Pro 12 ай тегін",
      intro: "Платформаның құқықтық дәлдігіне жауапты заңгерлер. Әр сценарий (мысалы, «тауар үшін ақшаны қайтару») — құжаттардың, мерзімдердің және алушылардың дайын тізбегі. Сарапшы оны тексеріп, өз атымен қол қояды.",
      doesTitle: "Сарапшы не істейді",
      does: ["Өз саласындағы сценарийдің нормаларын, мерзімдерін және алушыларын тексереді.", "Құжат үлгілерін тексереді (талап-арыз, шағым, өтініш).", "Заң өзгерсе, сценарийді жаңартады.", "Даулы жағдайларды әдістеме бойынша қарайды."],
      getsTitle: "Сарапшы не алады",
      gets: ["Pro 12 ай тегін.", "«Сарапшы» мәртебесі және тексерген әр сценарийде аты: «Сценарийді тексерген: …».", "Өз сценарийлері бойынша істерді бірінші алады.", "Konsilier.AI материалдары мен әлеуметтік желілерінде аталады."],
    },
    pricing: {
      title: "Тарифтер",
      basic: "Базалық",
      basicText: "Профиль, мәртебені тексеру, істерге жауап (айлық лимит), рейтинг.",
      proChip: "Серіктестерге 6 ай, сарапшыларға 12 ай тегін",
      proText: "Жауап лимитсіз, тізімде басымдық, ЖИ-жобалар, мерзім бақылау, өз клиенттеріңіздің CRM-і.",
      ngo: "Құқық қорғаушылар мен ҮЕҰ",
      ngoPrice: "0 ₸ мәңгі",
      ngoText: "Pro bono үшін Pro-мүмкіндіктер және донорларға көмек есептері.",
    },
    faqTitle: "Сұрақтар",
  },
};

type Text = (typeof TEXT)["ru"];

function useText(): Text {
  const { lang } = useLang();
  return TEXT[lang] as Text;
}

function Calculator() {
  const L = useText().calc;
  const [cases, setCases] = useState(8);
  const [check, setCheck] = useState(60000);
  const hours = cases * 1.5;
  const income = cases * check;
  return (
    <div className="card space-y-4">
      <h3 className="text-lg font-semibold">{L.title}</h3>
      <label className="block text-sm">
        {L.cases}: <b>{cases}</b>
        <input type="range" min={1} max={40} value={cases} onChange={(e) => setCases(+e.target.value)} className="h-8 w-full accent-[#1f6f5c]" />
      </label>
      <label className="block text-sm">
        {L.fee}: <b>{check.toLocaleString("ru-RU")} ₸</b>
        <input type="range" min={10000} max={500000} step={5000} value={check} onChange={(e) => setCheck(+e.target.value)} className="h-8 w-full accent-[#1f6f5c]" />
      </label>
      <div className="grid grid-cols-2 gap-3 text-center">
        <div className="rounded-xl bg-brand/10 p-3">
          <div className="text-xl font-bold text-brand sm:text-2xl">{income.toLocaleString("ru-RU")} ₸</div>
          <div className="text-xs text-ink/60">{L.income}</div>
        </div>
        <div className="rounded-xl bg-ink/5 p-3">
          <div className="text-xl font-bold sm:text-2xl">{hours.toLocaleString("ru-RU")} {L.hoursUnit}</div>
          <div className="text-xs text-ink/60">{L.hours}</div>
        </div>
      </div>
      <p className="text-xs text-ink/50">{L.note}</p>
    </div>
  );
}

function DossierPreview() {
  const L = useText().dossier;
  return (
    <div className="card space-y-3 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="chip bg-brand/10 text-brand">{L.chip}</span>
        <span className="text-xs text-ink/50">{L.example}</span>
      </div>
      <h3 className="text-base font-semibold">{L.title}</h3>
      <dl className="grid grid-cols-2 gap-2">
        {L.rows.map(([k, v]) => (
          <div key={k} className="rounded-lg bg-ink/5 p-2">
            <dt className="text-xs text-ink/50">{k}</dt>
            <dd className="font-medium">{v}</dd>
          </div>
        ))}
      </dl>
      <p className="text-xs text-ink/60">{L.hidden}</p>
      <div className="flex flex-wrap gap-2">
        <button className="btn-primary" disabled>{L.respond}</button>
        <button className="btn-ghost" disabled>{L.ask}</button>
      </div>
    </div>
  );
}

function ShareCard({ name, demo }: { name: string; demo: boolean }) {
  const L = useText().card;
  return (
    <div className="mx-auto w-full max-w-sm rounded-3xl bg-gradient-to-br from-[#1f6f5c] to-[#14213d] p-5 text-white shadow-lg">
      <div className="text-xs uppercase tracking-widest opacity-70">
        Konsilier.AI · {demo ? L.sample : L.partner}
      </div>
      <div className="mt-3 text-xl font-bold">{demo ? "Айгерим Н." : name}</div>
      <div className="text-sm opacity-80">{L.spec}</div>
      {demo ? (
        <div className="mt-4 flex items-end justify-between">
          <div>
            <div className="text-4xl font-bold">84</div>
            <div className="text-xs opacity-70">{L.score}</div>
          </div>
          <div className="text-right text-sm">
            <div><b>134</b> {L.cases}</div>
            <div><b>71 {L.mln} ₸</b> {L.recovered}</div>
          </div>
        </div>
      ) : (
        <div className="mt-4 text-sm opacity-90">{L.pending}</div>
      )}
      <div className="mt-4 rounded-xl bg-white/10 p-2 text-center text-xs">{L.footer}</div>
    </div>
  );
}

function ApplyForm() {
  const L = useText().form;
  const [form, setForm] = useState({
    full_name: "", kind: "advocate", organization: "", license_number: "", city: "", contact: "", message: "",
  });
  const [wantsExpert, setWantsExpert] = useState(false);
  const [spec, setSpec] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<{ referral_code: string } | null>(null);
  const [ref, setRef] = useState<string | null>(null);
  // Read ?ref= after mount (no Suspense needed, so the page prerenders fully and shows instantly).
  useEffect(() => setRef(new URLSearchParams(window.location.search).get("ref")), []);

  const link = useMemo(
    () => (done && typeof window !== "undefined" ? `${window.location.origin}/for-lawyers?ref=${done.referral_code}` : ""),
    [done],
  );

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const out = await publicApi<{ referral_code: string }>("/v1/lawyer-applications", {
        method: "POST",
        body: JSON.stringify({ ...form, country: "KZ", specializations: spec, referred_by: ref, wants_expert: wantsExpert }),
      });
      setDone(out);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  if (done) {
    return (
      <div className="card space-y-4">
        <h3 className="text-xl font-bold">{L.doneTitle}</h3>
        <p className="text-sm text-ink/70">{L.doneText}</p>
        <div className="flex flex-col gap-2 sm:flex-row">
          <input className="input" readOnly value={link} onFocus={(e) => e.target.select()} />
          <button className="btn-ghost shrink-0" onClick={() => navigator.clipboard?.writeText(link)}>{L.copy}</button>
        </div>
        <div className="flex flex-wrap gap-2">
          <a className="btn-primary" target="_blank" rel="noreferrer" href={`https://wa.me/?text=${encodeURIComponent(L.share + link)}`}>WhatsApp</a>
          <a className="btn-primary" target="_blank" rel="noreferrer" href={`https://t.me/share/url?url=${encodeURIComponent(link)}&text=${encodeURIComponent(L.share)}`}>Telegram</a>
          <a className="btn-ghost" target="_blank" rel="noreferrer" href={`https://www.linkedin.com/sharing/share-offsite/?url=${encodeURIComponent(link)}`}>LinkedIn</a>
        </div>
        <ShareCard name={form.full_name} demo={false} />
      </div>
    );
  }

  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setForm({ ...form, [k]: e.target.value });

  return (
    <form onSubmit={submit} className="card space-y-3">
      <h3 className="text-xl font-bold">{L.title}</h3>
      {ref && <p className="chip bg-brand/10 text-brand">{L.invited}</p>}
      <input className="input" required minLength={3} placeholder={L.name} value={form.full_name} onChange={set("full_name")} />
      <select className="input" value={form.kind} onChange={set("kind")}>
        {L.kinds.map(([k, label]) => <option key={k} value={k}>{label}</option>)}
      </select>
      <div className="grid gap-3 sm:grid-cols-2">
        <input className="input" placeholder={L.org} value={form.organization} onChange={set("organization")} />
        <input className="input" placeholder={L.license} value={form.license_number} onChange={set("license_number")} />
        <input className="input" placeholder={L.city} value={form.city} onChange={set("city")} />
        <input className="input" required minLength={3} placeholder={L.contact} value={form.contact} onChange={set("contact")} />
      </div>
      <div className="flex flex-wrap gap-2">
        {L.specs.map(([k, label]) => (
          <button
            type="button"
            key={k}
            onClick={() => setSpec(spec.includes(k) ? spec.filter((s) => s !== k) : [...spec, k])}
            className={`chip min-h-10 px-3 py-2 text-sm ${spec.includes(k) ? "bg-brand text-white" : ""}`}
          >
            {label}
          </button>
        ))}
      </div>
      <label className="flex items-start gap-2 text-sm">
        <input type="checkbox" className="mt-0.5 h-5 w-5 shrink-0 accent-brand" checked={wantsExpert} onChange={(e) => setWantsExpert(e.target.checked)} />
        <span>{L.expert}</span>
      </label>
      <textarea className="input" rows={2} placeholder={L.message} value={form.message} onChange={set("message")} />
      <button className="btn-primary w-full py-3 text-base" disabled={busy}>{busy ? L.busy : L.submit}</button>
      {error && <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-red-700">{error}</p>}
      <p className="text-xs text-ink/50">{L.privacy}</p>
    </form>
  );
}

export default function ForLawyers() {
  const L = useText();
  return (
    <div className="space-y-16">
      {/* HERO */}
      <section className="grid gap-8 pt-4 md:grid-cols-[1.3fr_1fr] md:items-center">
        <div className="space-y-5">
          <span className="chip bg-brand/10 text-brand">{L.hero.chip}</span>
          <h1 className="text-3xl font-bold leading-tight md:text-4xl">{L.hero.title}</h1>
          <p className="text-lg text-ink/70">{L.hero.sub}</p>
          <div className="flex flex-wrap gap-3">
            <a href="#apply" className="btn-primary px-6 py-3 text-base">{L.hero.apply}</a>
            <a href="/lawyers" className="btn-ghost px-6 py-3 text-base">{L.hero.rating}</a>
          </div>
          <p className="text-sm text-ink/60">{L.hero.perks}</p>
        </div>
        <DossierPreview />
      </section>

      {/* PAINS → FIX */}
      <section className="space-y-4">
        <h2 className="text-2xl font-bold">{L.painsTitle}</h2>
        <div className="grid gap-4 md:grid-cols-3">
          {L.pains.map(([pain, fix]) => (
            <div key={pain} className="card space-y-2">
              <p className="text-sm text-red-700">✗ {pain}</p>
              <p className="text-sm">✓ {fix}</p>
            </div>
          ))}
        </div>
      </section>

      {/* BENEFITS */}
      <section className="space-y-4">
        <h2 className="text-2xl font-bold">{L.benefitsTitle}</h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {L.benefits.map(([icon, title, text, soon]) => (
            <div key={title} className="card space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-2xl">{icon}</span>
                <h3 className="font-semibold">{title}</h3>
                {soon && <span className="chip bg-amber-100 text-amber-900">{L.soon}</span>}
              </div>
              <p className="text-sm text-ink/70">{text}</p>
            </div>
          ))}
        </div>
      </section>

      {/* CALCULATOR + SHARE CARD */}
      <section className="grid gap-6 md:grid-cols-2 md:items-center">
        <Calculator />
        <div className="space-y-3">
          <h2 className="text-2xl font-bold">{L.reputationTitle}</h2>
          <p className="text-ink/70">{L.reputation}</p>
          <ShareCard name="" demo />
        </div>
      </section>

      {/* GROWTH LOOP */}
      <section className="space-y-4">
        <h2 className="text-2xl font-bold">{L.growthTitle}</h2>
        <div className="grid gap-4 md:grid-cols-4">
          {L.growth.map(([icon, title, text]) => (
            <div key={title} className="card space-y-1">
              <div className="text-2xl">{icon}</div>
              <h3 className="font-semibold">{title}</h3>
              <p className="text-sm text-ink/70">{text}</p>
            </div>
          ))}
        </div>
      </section>

      {/* PARTNER PROGRAMME */}
      <section className="space-y-4">
        <h2 className="text-2xl font-bold">{L.partner.title}</h2>
        <p className="text-ink/70">{L.partner.intro}</p>
        <div className="grid gap-4 md:grid-cols-2">
          <div className="card space-y-2">
            <h3 className="font-semibold">{L.partner.doesTitle}</h3>
            <ul className="list-inside list-disc space-y-1 text-sm text-ink/70">
              {L.partner.does.map((x) => <li key={x}>{x}</li>)}
            </ul>
          </div>
          <div className="card space-y-2 border-brand ring-2 ring-brand/20">
            <h3 className="font-semibold">{L.partner.getsTitle}</h3>
            <ul className="list-inside list-disc space-y-1 text-sm text-ink/70">
              {L.partner.gets.map((x) => <li key={x}>{x}</li>)}
            </ul>
          </div>
        </div>
        <p className="text-xs text-ink/50">{L.partner.lose}</p>
        <div className="space-y-3 rounded-2xl bg-ink p-5 text-white shadow-sm">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-lg font-semibold">{L.expert.title}</h3>
            <span className="chip bg-white/15 text-white">{L.expert.chip}</span>
          </div>
          <p className="text-sm text-white/80">{L.expert.intro}</p>
          <div className="grid gap-4 md:grid-cols-2">
            <ul className="list-inside list-disc space-y-1 text-sm text-white/80">
              <li className="list-none font-semibold text-white">{L.expert.doesTitle}</li>
              {L.expert.does.map((x) => <li key={x}>{x}</li>)}
            </ul>
            <ul className="list-inside list-disc space-y-1 text-sm text-white/80">
              <li className="list-none font-semibold text-white">{L.expert.getsTitle}</li>
              {L.expert.gets.map((x) => <li key={x}>{x}</li>)}
            </ul>
          </div>
        </div>
      </section>

      {/* PRICING */}
      <section className="space-y-4">
        <h2 className="text-2xl font-bold">{L.pricing.title}</h2>
        <div className="grid gap-4 md:grid-cols-3">
          <div className="card space-y-2">
            <h3 className="font-semibold">{L.pricing.basic}</h3>
            <div className="text-2xl font-bold">0 ₸</div>
            <p className="text-sm text-ink/70">{L.pricing.basicText}</p>
          </div>
          <div className="card space-y-2 border-brand ring-2 ring-brand/20">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="font-semibold">Pro</h3>
              <span className="chip bg-brand text-white">{L.pricing.proChip}</span>
            </div>
            <div className="text-2xl font-bold">{L.proPrice}</div>
            <p className="text-sm text-ink/70">{L.pricing.proText}</p>
          </div>
          <div className="card space-y-2">
            <h3 className="font-semibold">{L.pricing.ngo}</h3>
            <div className="text-2xl font-bold">{L.pricing.ngoPrice}</div>
            <p className="text-sm text-ink/70">{L.pricing.ngoText}</p>
          </div>
        </div>
      </section>

      {/* FAQ + FORM */}
      <section id="apply" className="grid gap-6 md:grid-cols-2">
        <div className="space-y-3">
          <h2 className="text-2xl font-bold">{L.faqTitle}</h2>
          {L.faq.map(([q, a]) => (
            <details key={q} className="card">
              <summary className="cursor-pointer font-semibold">{q}</summary>
              <p className="mt-2 text-sm text-ink/70">{a}</p>
            </details>
          ))}
        </div>
        <ApplyForm />
      </section>
    </div>
  );
}
