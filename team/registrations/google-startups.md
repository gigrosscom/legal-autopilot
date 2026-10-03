# Google for Startups Cloud Program — пакет заявки Konsiliér AI

Ведёт «Документация».

Подготовлено 30.09.2026 («Документация»). **Заявка не подана, аккаунты не созданы.** Подача — только после «да»
владельца (решение 30.09: очерёдность NVIDIA → Astana Hub (G-TON отменён 01.10) → AWS Activate → Google for Startups).
Все официальные страницы проверены **30.09.2026** (скачаны и прочитаны целиком, английская версия `?hl=en`).
Неофициальные источники помечены «проверить».

---

## 0. Коротко

| Вопрос | Ответ |
|---|---|
| Что даёт нам (реально) | **Start tier: до $2 000 кредитов Google Cloud на 12 месяцев**, $200 на Google Skills, 12 мес. Google Workspace Business Plus (если домен не на платном Workspace), перки партнёров. Кредиты покрывают модели Google (Gemini, Gemma) и Gemini API |
| $200 000 / $350 000 (AI) | **Нам сейчас недоступно.** Scale tier и AI-программа — только для стартапов с equity-инвестициями от институционального инвестора/VC (pre-seed–Series A). У нас инвестиций 0 |
| Стоимость | Платы за подачу на официальных страницах нет. Но нужен **Cloud Billing account** с платёжным способом (карта); для Gemini API на Prepay — пополнение от $5 до использования кредитов |
| Срок | Приём постоянный, дедлайнов нет. Ответ «обычно за несколько рабочих дней», при ручной проверке 10+ дней |
| Блокеры | 1) нет Google-аккаунта/Cloud Billing на домене konsilier.com (почта заявки, домен сайта и домен billing-аккаунта должны совпадать); 2) Start tier требует «plans to seek venture funding soon» — владелец должен подтвердить; 3) «да» владельца на подачу; 4) выбор страны billing-аккаунта нельзя поменять потом |
| Главный риск | Одобрение «на усмотрение Google»; явного списка допущенных стран в программе нет (Казахстан не запрещён) |

---

## 1. Условия (официальные источники, проверено 30.09.2026)

### 1.1. Уровни и кредиты

| Уровень | Для кого (цитата) | Кредиты | Источник |
|---|---|---|---|
| **Start** | «For digital-native startups with a working MVP, a clear business model, and plans to seek venture funding soon» | «Up to $2,000 USD in Google Cloud credits, valid for one year»; $200 Google Skills; Workspace Business Plus 12 мес. | [cloud.google.com/startup/benefits](https://cloud.google.com/startup/benefits), [cloud.google.com/startup/pre-funded](https://cloud.google.com/startup/pre-funded) |
| **Scale** | «For VC-funded startups ready to grow and scale» | До $200 000 за 2 года: год 1 — «100% up to $100,000», год 2 — «20% up to an additional $100,000»; $12 000 Enhanced Support; $500 Skills | [benefits](https://cloud.google.com/startup/benefits), [early-stage](https://cloud.google.com/startup/early-stage) |
| **AI (Scale для AI-first)** | «A program designed for Scale tier AI startups»; «Startups that use or plan to use Gemini Enterprise or Gemini to deploy AI services as a foundation of their primary product» | До $350 000: год 1 — «100% up to $250,000», год 2 — как Scale | [cloud.google.com/startup/ai](https://cloud.google.com/startup/ai) |
| Series B+ | Индивидуальные условия, не для нас | — | [cloud.google.com/startup](https://cloud.google.com/startup) |

AI-трек **не отдельный уровень для pre-funded**: это надстройка над Scale, те же требования к инвестициям
([startup/ai](https://cloud.google.com/startup/ai), FAQ: «up to $350,000 USD for Scale tier AI startups» —
[startup/faq](https://cloud.google.com/startup/faq)). Критерий AI-first: «having AI built into your startup's
foundational structure and strategy and not only as a productivity/bolt-on layer» (FAQ).

### 1.2. Требования и наше соответствие

| Требование (официально) | Konsiliér AI | Источник |
|---|---|---|
| Start: «Founded within the last 24 months» | ТОО зарегистрировано 29.09.2026 — да | [benefits](https://cloud.google.com/startup/benefits) |
| Start: «Not yet received Google Cloud credits (beyond the free trial)» | Кредитов не получали (подтвердить владельцу) | там же |
| Start: «working MVP, a clear business model, and plans to seek venture funding soon»; «Demonstrate a well-defined product roadmap» | MVP запущен 09.2026, модель — оплата за документ. **«Planning to seek venture funding» — нужно подтверждение владельца** | [pre-funded](https://cloud.google.com/startup/pre-funded) |
| «Excluding service agencies, consultancies, and traditional small businesses» | Мы ИТ-продукт, не юрфирма и не консалтинг — так и формулировать | [pre-funded](https://cloud.google.com/startup/pre-funded) (сноска **) |
| Scale/AI: «recent startup equity funding from pre-seed to Series A by an institutional investor»; «Funding via private equity, government innovation grants, prize funding, crowdfunding, angel, and friends & family funding will not qualify a startup for Scale» | Инвестиций 0 → **Scale/AI недоступны**. Гранты (G-TON, Astana Hub) тоже не дадут Scale | [early-stage](https://cloud.google.com/startup/early-stage), [benefits](https://cloud.google.com/startup/benefits) |
| Scale: «Not yet received more than $5,000 in Google Cloud credits» | Start ($2 000) не закрывает путь в Scale позже — вывод из текста, прямого правила «апгрейда» нет | [benefits](https://cloud.google.com/startup/benefits) |
| «Have your 18-character Google Cloud billing account ID and ensure the business email in your application matches your startup's public website domain» | Сайт konsilier.com, почта dev@konsilier.com. Billing account ещё нет | [faq](https://cloud.google.com/startup/faq) |
| «your company website domain must match your email domain and the email domain associated with your billing account» | Billing account нужно создавать из Google-аккаунта на `@konsilier.com` | [faq](https://cloud.google.com/startup/faq) |
| Кого не берут: IPO/поглощённые, учебные заведения, госорганы, НКО, личные блоги, дев-шопы, консалтинг, агентства, криптомайнинг | Не про нас | [faq](https://cloud.google.com/startup/faq) |
| Решение — «at the discretion of Google Cloud»; в условиях: Google может отказать «for reasons such as the geographic region or country of the Company's primary place of business» | Риск, но не запрет | [benefits](https://cloud.google.com/startup/benefits), [terms/startup-program-tos](https://cloud.google.com/terms/startup-program-tos) |
| Workspace-перк: домен не должен быть на платном Workspace в течение 31 дня до заявки | Нужно знать, где почта konsilier.com | [pre-funded](https://cloud.google.com/startup/pre-funded) |

### 1.3. Казахстан

- Списка допущенных стран у программы на официальных страницах **нет**. Онбординг перечисляет только ограничения
  Google Cloud: «such as China, Crimea, Cuba, Iran, North Korea, and Syria» — Казахстана там нет
  ([startup/onboarding](https://cloud.google.com/startup/onboarding)).
- Старые версии условий ссылались на «Territory» по `cloud.google.com/gcp-territory-list`; текущая страница этого
  списка стран не содержит (только отсылка к Program Guide для партнёров), текущие условия
  ([startup-program-tos](https://cloud.google.com/terms/startup-program-tos)) территорию не упоминают.
- Kazakhstan есть в списке стран Gemini API ([ai.google.dev/gemini-api/docs/available-regions](https://ai.google.dev/gemini-api/docs/available-regions)).
- Тенге нет в списке валют Cloud Billing ([docs.cloud.google.com/billing/docs/resources/currency](https://docs.cloud.google.com/billing/docs/resources/currency)) —
  вероятно, счёт будет в USD. **Проверить** при создании billing-аккаунта (страну и валюту потом не изменить —
  [onboarding](https://cloud.google.com/startup/onboarding)).

### 1.4. Покрывают ли кредиты Gemini API / Vertex AI

| Вопрос | Ответ | Источник |
|---|---|---|
| Модели Google | «Program credits cover Google's state-of-the-art models like Gemini and Gemma» (Start: «cover proprietary Google models») | [benefits](https://cloud.google.com/startup/benefits), [pre-funded](https://cloud.google.com/startup/pre-funded) |
| Gemini API (AI Studio) | «Cloud credits (from $2k to potentially $350k), to use towards your Gemini API usage» | [startup.google.com/gemini](https://startup.google.com/gemini/) |
| Нюанс Prepay | «If you have a prepay billing account, you must add funds to your account before you can use promotional Cloud Credits» — минимум $5 при настройке | [ai.google.dev/gemini-api/docs/billing](https://ai.google.dev/gemini-api/docs/billing) |
| Vertex AI | С 2026 называется **Gemini Enterprise Agent Platform (formerly Vertex AI)**; это сервис Google Cloud, кредиты применяются к Google Cloud services | [cloud.google.com/products/gemini-enterprise-agent-platform](https://cloud.google.com/products/gemini-enterprise-agent-platform), сноска 1 на [benefits](https://cloud.google.com/startup/benefits) |
| Сторонние модели (Claude и др. в Model Garden) | «Third-party models are billed directly and are not covered by the program credits» — **документы на Claude кредитами не оплатить** | [faq](https://cloud.google.com/startup/faq), [ai](https://cloud.google.com/startup/ai) |
| Бесплатный пробный период $300 | Не покрывает Gemini API с марта 2026 | [gemini-api/docs/billing](https://ai.google.dev/gemini-api/docs/billing) |

### 1.5. Два факта из условий Gemini API, важных для нас (владельцу к сведению)

Источник: [ai.google.dev/gemini-api/terms](https://ai.google.dev/gemini-api/terms), 30.09.2026.
- Бесплатная квота: «Google uses the content you submit… human reviewers may read, annotate, and process your API
  input and output… Do not submit sensitive, confidential, or personal information to the Unpaid Services.» Чат
  сейчас на бесплатном Gemini; мы обезличиваем данные, но это ещё один довод за платный уровень. Ничего не меняю —
  решение за владельцем.
- «You may not use the Services to develop models that compete with the Services». В заявке Zann описан как
  дообучение открытых моделей на официальных текстах законов, **не на ответах Gemini** — так и нужно строить.

---

## 2. Какой уровень подаём и почему

**Подаём в Start tier ($2 000, 12 месяцев). AI-трек и Scale — не подаём сейчас.**
- Scale и AI требуют equity-инвестиций от институционального инвестора/VC; у нас 0, а гранты и ангелы не
  засчитываются (официально, раздел 1.2).
- Форма сама подбирает уровень («Eligible startups will be matched with the tier… that best suit the stage»); в
  тексте всё равно подчеркнуть, что Gemini — основа продукта (AI-first): это пригодится для перевода в AI-трек
  после первого институционального раунда.
- $2 000 не решает проблему «~200–600 активных пользователей в день» надолго. Сколько дней чата это покроет, не
  считаю: нужны текущие цены Gemini и наш фактический расход токенов — **отдельный расчёт**.
- Порог Scale «не более $5 000 кредитов» — Start ($2 000) его не нарушает.

---

## 3. Поля формы — готовые ответы (EN)

Форма открывается только после входа в Google-аккаунт (`cloud.google.com/startup/apply` перенаправляет на
accounts.google.com — проверено 30.09.2026), поэтому **точный список полей официально не подтверждён**. Состав ниже —
из официального FAQ (billing ID, почта домена) и неофициальных обзоров (**проверить** на месте). Поля, которых
не окажется в форме, пропустить; незнакомые — заполнить из текстов ниже.

### Контакт
| Поле | Ответ |
|---|---|
| First name / Last name | Nurlan / Khabibulla (сверить с паспортом) |
| Business email | dev@konsilier.com |
| Business phone | `[владелец]` |
| Job title | Founder & CTO |
| Job role / function | Engineering / Technical founder (ближайший вариант) |
| LinkedIn (если спросят) | https://www.linkedin.com/in/khabibulla |

### Компания
| Поле | Ответ |
|---|---|
| Company name | Konsilier AI LLP |
| Website | https://konsilier.com |
| Company LinkedIn | https://www.linkedin.com/company/konsilier/ |
| Country | Kazakhstan |
| HQ address | Akseleu Seidimbek st. 222, Kuramys microdistrict, Nauryzbay district, Almaty 050000, Kazakhstan |
| Registration / tax ID (если спросят) | BIN 260940036818 |
| Founded / incorporation date | 29 September 2026 (вариант «within the last 90 days» / «less than 1 year», если выбор из диапазонов) |
| Number of employees | 2 |
| Industry | Legal tech / Consumer software (ближайший вариант; не «Professional services / Consulting») |
| Funding stage | Pre-funded / Bootstrapped / No funding |
| Total funding raised | 0 USD |
| Investors / funding verification links | None |
| Annual revenue | None yet (pre-revenue) |
| Plan to raise venture funding soon? | Yes (владелец, 30.09.2026) |
| Google Cloud billing account ID (18 символов) | `[после создания billing-аккаунта, формат XXXXXX-XXXXXX-XXXXXX]` |
| Received Google Cloud credits before? | No (кроме free trial, если будет) — подтвердить владельцу |
| Second contact (если есть поле) | Saltanat Tulegenova, CEO, saltanat@konsilier.com |

### Тексты

**Company / product description (~560 символов):**
> Konsiliér AI is an AI legal assistant for people and small businesses in Kazakhstan, launched in September 2026 as a web app, an installable PWA and a Telegram bot. A free AI chat explains a user's rights in plain language and links every cited law to its official text on adilet.zan.kz. When action is needed, the user can buy a ready-to-file document under Kazakh law (claim, complaint, application) for KZT 1,990, or a full-case package for KZT 9,990. Personal data is de-identified before any text is sent to a language model. It is a software product, not a law firm.

**How is AI core to your product? (AI-first):**
> AI is the product, not an add-on. Every user interaction starts in an AI chat that understands a legal problem described in Russian or Kazakh, maps it to one of 20 published Kazakhstan scenarios, and explains the relevant rules with links to official law texts. The chat runs on Google Gemini today. Documents are drafted by a language model from structured scenarios. Our roadmap is our own Russian/Kazakh legal language model, "Zann", built by fine-tuning open models on official legal texts.

**How will you use Google Cloud / the credits?**
> Today our chat runs on the free Gemini API tier, which limits us to roughly 200–600 active users per day and is not meant for sensitive user content. Credits would let us (1) move the chat to paid Gemini on Google Cloud (Gemini API / Gemini Enterprise Agent Platform) for reliable capacity and paid-tier data terms, and (2) run first fine-tuning experiments for Zann on Google's open Gemma models. Our application servers stay in Yandex Cloud, Kazakhstan region; Google Cloud would host our AI workloads.

**Product roadmap / vision (если спросят):**
> Now: Kazakhstan, 20 published legal scenarios, pay-per-document. Next: the Zann legal language model for Russian and Kazakh, then country packs for Central Asia, the Caucasus, Turkey and MENA, reusing the same scenario engine with local laws.

**Business model (если спросят):**
> Free AI chat; users pay per ready-to-file document (KZT 1,990) or per full-case package (KZT 9,990). No revenue yet.

**Traction (если поле обязательно):**
> Launched in September 2026; 20 Kazakhstan legal scenarios published; web app, PWA and Telegram bot live. Pre-revenue.

Правила текста соблюдены: нет юристов на платформе и «lawyer-reviewed», нет подписок, нет выдуманных пользователей,
партнёров, выручки. «200–600 users/day» — оценка ёмкости бесплатного уровня, не наша аудитория.

---

## 4. Что нужно от владельца

1. **«Да» на подачу** в Google for Startups (по очерёдности она последняя).
2. ~~Подтвердить планы на венчурные инвестиции~~ — **да**, владелец 30.09.2026.
3. **Google-аккаунт на `dev@konsilier.com`** (обычный Google-аккаунт с существующей почтой, без Gmail) — создаёт
   владелец/Нурлан. Где сейчас ключ бесплатного Gemini — на каком аккаунте? Лучше перенести проект на этот аккаунт.
4. **Cloud Billing account** под этим аккаунтом: страна Kazakhstan, тип профиля Business, юрлицо Konsilier AI LLP,
   БИН; нужна карта. Прислать 18-значный Billing Account ID (это не секрет, но и не публичные данные).
5. Телефон для формы.
6. Где хостится почта konsilier.com (Google Workspace платный? другое?) — от этого зависит перк Workspace.
7. Подтвердить: Google Cloud-кредитов ранее не получали.
8. Согласовать тексты раздела 3 (особенно фразы про free tier и данные).

---

## 5. Пошагово (выполняет владелец после «да»)

1. Записать решение в `team/decisions.md`.
2. Войти/создать Google-аккаунт на dev@konsilier.com → [console.cloud.google.com](https://console.cloud.google.com).
3. Billing → Manage billing accounts → Create account: страна Kazakhstan (нельзя изменить), Business-профиль,
   платёжный способ → Submit and enable billing ([инструкция](https://cloud.google.com/startup/onboarding)).
   Скопировать Billing Account ID.
4. Открыть [cloud.google.com/startup/apply](https://cloud.google.com/startup/apply), войти тем же аккаунтом;
   проверить, что подставился правильный billing ID.
5. Заполнить поля по разделу 3. Скриншот подтверждения — в папку «Konsilier» на Google Drive.
6. Ждать ответ (несколько рабочих дней, до 10+). При отказе — cloudstartupsupport@google.com ([faq](https://cloud.google.com/startup/faq)).
7. После одобрения: Cloud Identity/организация по [onboarding](https://cloud.google.com/startup/onboarding);
   привязать проект Gemini к billing-аккаунту с кредитами; при Prepay — пополнить минимум и проверить, что кредиты
   списываются первыми ([billing](https://ai.google.dev/gemini-api/docs/billing)); отдельно заявить Workspace-перк.
8. Переключение чата на платный Gemini — решение владельца и задача «Интеграции» (записать в decisions.md и
   product.md).
9. После первого институционального раунда — запросить перевод в Scale/AI (до $350 000).

---

## Источники

Официальные (все открыты 30.09.2026):
- https://cloud.google.com/startup — уровни, суммы
- https://cloud.google.com/startup/benefits — требования и выгоды по уровням, сноски
- https://cloud.google.com/startup/pre-funded — Start tier, $2 000, 12 месяцев
- https://cloud.google.com/startup/early-stage — Scale tier, институциональный инвестор
- https://cloud.google.com/startup/ai — AI-программа, до $350 000
- https://cloud.google.com/startup/faq — billing ID, домен почты, AI-first, сторонние модели, сроки ответа
- https://cloud.google.com/startup/onboarding — billing-аккаунт, страна, запрещённые территории
- https://cloud.google.com/terms/startup-program-tos — условия программы
- https://cloud.google.com/startup/apply — форма (требует входа)
- https://startup.google.com/gemini/ — кредиты на Gemini API
- https://ai.google.dev/gemini-api/docs/billing — Prepay, кредиты, free trial
- https://ai.google.dev/gemini-api/terms — данные на бесплатной квоте, запрет конкурирующих моделей
- https://ai.google.dev/gemini-api/docs/available-regions — Kazakhstan в списке
- https://docs.cloud.google.com/billing/docs/resources/currency — валюты Cloud Billing (KZT нет)
- https://cloud.google.com/products/gemini-enterprise-agent-platform — Vertex AI переименован

Неофициальные (**проверить**; использованы только для догадки о полях формы):
- https://www.stackmatix.com/blog/google-for-startup-program (02.09.2026)
- https://tryhaystack.ai/google-for-startups-cloud-program-what-you-should-know/
- https://gist.github.com/eonist/ecad3f8caba878e305e4dbf42536bfc4 (30.06.2025)

## Статус 01.10.2026
- Создание Cloud Billing отклонено автоматической проверкой Google: ошибка **OR_BACR2_59** (организация Workspace «Konsilier AI», страна KZ, карта Visa).
- Владелец отправил обращение GCP Account Suspension Inquiry (support.google.com/cloud/contact/cloud_platform_suspensions) 01.10.2026 ~03:00 Алматы; ответ — до 48 ч на dev@konsilier.com.
- До ответа: не повторять попытки с другими картами. Заявку в Google for Startups подаём после появления billing-аккаунта.
