# AWS Activate: пакет заявки Konsilier AI

Ведёт «Документация».

Подготовлено 30.09.2026. Все условия проверены 30.09.2026 по официальным страницам AWS (ссылки в конце, [S1]…[S8]).
Всё, что взято не с сайта AWS, помечено **«проверить»**. Ничего не подано, аккаунты не создавались.
По решению владельца от 30.09 AWS Activate идёт **четвёртым** в очереди (NVIDIA → Astana Hub (G-TON отменён 01.10) → AWS Activate → Google). Подаём только после отдельного «да» владельца.

---

## 0. Коротко

| | |
|---|---|
| **Что даёт** | Activate Founders: **$1 000** кредитов AWS на старте; «select participants» могут получить до **$5 000** со временем [S1][S2]. Кредиты можно тратить на **Claude (Anthropic) в Amazon Bedrock** [S3][S4]. |
| **Стоимость** | Сама заявка бесплатная [S3: «Free to join»]. Нужен AWS-аккаунт на **платном плане (Paid plan)** с действующим способом оплаты. Всё, что не покрыто кредитами, списывается с карты по обычным тарифам [S5][S6]. |
| **Срок подачи** | Фиксированного срока нет, приём идёт постоянно. Рассмотрение: 7–10 рабочих дней по FAQ [S3], 5–10 по странице кредитов [S1]. Кредиты действуют ограниченное время, «обычно 1–2 года» [S2]. |
| **Блокеры** | 1) Нет AWS-аккаунта на Paid plan с картой, а email аккаунта должен быть на домене @konsilier.com. 2) У сайта нет `robots.txt` (отдаётся 404), а AWS проверяет сайт роботом. 3) В meta description главной есть фраза «поможет найти юриста» — это расходится с правилом «юристов на платформе нет». 4) Ссылка на LinkedIn в подвале сайта (`/company/konsilier.ai`) не совпадает с той, что дал владелец (`/company/konsilier/`). 5) Если сначала взять Founders, это может помешать получить AWS-перк через Astana Hub (**проверить**, см. §2). 6) Компании один день. Минимального возраста AWS не называет, но держите под рукой свидетельство о регистрации на случай апелляции [S3, ReasonCode_12]. |

---

## 1. Условия (с источниками, проверено 30.09.2026)

**Уровни программы**
- **Activate Founders** (self-funded, bootstrapped): старт $1 000, для «select participants» до $5 000. Подаётся напрямую, без Org ID [S1][S2].
- **Activate Portfolio** (до Series B): до $200 000. Нужен **Org ID от Activate Provider** (акселератор, VC, ангел). Один Org ID можно использовать один раз [S1][S3].
- **AWS Credits for AI Startups**: $200 000+, только по приглашению после Portfolio [S1]. Нам не подходит.

**Общие требования** [S1][S2][S3]
- До Series B включительно. FAQ формулирует так: «bootstrapped, self-funded, and funded startups up to and including Series A» [S3].
- Компания основана в последние 10 лет [S1][S2][S3].
- Сайт или публичный профиль работает. На сайте не должно быть заглушек «under construction», «coming soon», maintenance, 404/500 или редиректов на другой сайт. Название компании на сайте должно совпадать с заявкой. Сайт должен пускать краулеры: тексты отказов прямо упоминают `robots.txt` [S3, rejection rules]. Подавая URL, вы разрешаете AWS автоматически собирать с сайта публичную информацию [S4, п. 1.1].
- **AWS-аккаунт на Paid Tier Plan**: «Free account plans are not eligible for Activate promotional credits» [S1][S3][S5].
- **Домен email в заявке и в AWS-аккаунте должен совпадать**. Бесплатные почтовые сервисы для бизнес-заявок не принимаются [S3, ReasonCode_20/31]. Руководство AWS: «use your business email address (matching your startup's domain)» [S2].
- AWS-аккаунт должен быть активен и не приостановлен [S3].
- Founders: компания раньше не получала Activate Credits [S2]. Повторная заявка возможна только на бо́льшую сумму, и тогда выдают разницу [S3].
- Одновременно можно держать только одну заявку [S3].
- Госорганизации и компании с господдержкой (majority-owned/controlled/«substantially funded by any government») не допускаются [S4, п. 1.1]. ТОО частное, под это не попадает.
- AWS может отклонить заявку по своему усмотрению [S4, п. 1.2].
- ReasonCode_15: «most recent funding round must be within 12 months». По руководству это условие «if applicable» и относится к Portfolio [S2][S3]. У нас инвестиций 0.

**Казахстан.** Официального списка допущенных или исключённых стран на страницах AWS Activate я **не нашёл**. В форме есть отказы «AWS Activate is not available in your country» и «…in your payer account's country», а также ReasonCode_21 «based on the region where your startup is located» [S3]. Значит, ограничения по странам существуют, но их список не опубликован. **Подтвердить допуск Казахстана по официальным источникам не удалось.** Косвенный признак: на странице Astana Hub «Hub Perks» есть перк AWS Activate [N1, **проверить**]. Anthropic включает Казахстан в список стран для коммерческого API [S8].

**Claude в Amazon Bedrock за счёт кредитов**
- FAQ: «AWS Activate Credits are also redeemable for third-party models on Amazon Bedrock … like … Anthropic» [S3].
- Условия Activate (Last Updated 22.01.2026), п. 1.2: кредиты «may be applied to offset fees and charges for AWS Marketplace incurred for the use of third-party foundation models available on Amazon Bedrock ("Bedrock 3P Model Spend")» [S4]. Общие Promotional Credit Terms (обновлены 24.09.2026) исключают AWS Marketplace [S6], но для Activate действует это исключение из исключения [S4].
- Для доступа к Claude в Bedrock нужно: один раз заполнить форму Anthropic **First Time Use** (описание сценария и сайт), выдать IAM-права `aws-marketplace:Subscribe/Unsubscribe/ViewSubscriptions` и указать **действующий способ оплаты для покупок в AWS Marketplace** [S7].
- Кредиты нельзя передавать конечным клиентам [S4]. Прошлые счета они не покрывают, только расходы с месяца зачисления [S3].

**Чего нельзя оплатить кредитами** [S3][S6]: Mechanical Turk, Managed Services, Professional Services, Training/Certification, регистрацию доменов в Route 53, майнинг, авансовые платежи за Savings Plans/Reserved Instances, прочий Marketplace (кроме моделей Bedrock), Enterprise Support.

**Сроки и порядок**: Builder ID → профиль Activate → выбор уровня → данные о стартапе → привязка и верификация AWS-аккаунта → отправка. Отправленную заявку нельзя редактировать, её можно только отменить и подать заново [S2][S3]. После одобрения кредиты сами зачисляются в аккаунт в течение 3–4 часов. Срок их действия виден в Billing → Credits [S2].

---

## 2. Какой уровень подаём и почему

**Подаём Activate Founders.** Внешних инвестиций 0, выручки нет, Org ID от провайдера у нас нет. По правилам AWS без Org ID доступен только Founders [S2: «If you do not have an Org ID, you are initially eligible for the Founders Package»].

Сравнение с текущим лимитом на Claude ($50/месяц): $1 000 покрывают до 20 месяцев расходов на уровне этого лимита. Это только арифметика, фактический расход и срок действия кредитов будут видны после зачисления.

**Portfolio через Astana Hub (на будущее).** На странице Astana Hub «Hub Perks» указано «up to $100,000» по AWS Activate [N1, **проверить**]. Является ли Astana Hub Activate Provider с Org ID, доступен ли перк только участникам технопарка и какая сумма, на сайте AWS **не подтверждено**. Правила AWS позволяют взять Founders сейчас, а позже подать на Portfolio на бо́льшую сумму и получить разницу [S3]. **Но** в пересказе поисковика со статьи Astana Hub говорится, что партнёрские ресурсы не дают тем, кто уже получал услуги партнёра или уже его клиент [N2, **проверить**]. Поэтому **до подачи Founders нужно спросить Astana Hub**, лишит ли нас Founders-кредит их AWS-перка. Если лишит, лучше дождаться Astana Hub и подать сразу Portfolio (по очереди владельца Astana Hub и так идёт раньше AWS).

---

## 3. Поля формы: готовые ответы (EN)

Официально AWS описывает содержание формы так: «business information (product, target market, current traction)», «current funding stage», «most recent funding date», профиль компании, выбор уровня, привязка AWS Account ID [S1][S2]. **Полного публичного списка полей нет.** Ниже ответы на поля, которые названы официально, и на обычные поля профиля. Точные названия и лимиты символов нужно сверить в самой форме.

| Поле | Ответ |
|---|---|
| Company / Startup name | Konsilier AI LLP |
| Product / brand name | Konsilier AI |
| Website | https://konsilier.com |
| Company LinkedIn | https://www.linkedin.com/company/konsilier/ |
| Country of incorporation / HQ | Kazakhstan |
| Registered address | 222 Akseleu Seidimbek St., Kuramys microdistrict, Nauryzbay district, Almaty 050000, Kazakhstan |
| Registration number (BIN) | 260940036818 |
| Founding / incorporation date | 29 September 2026 |
| Number of employees | 2 |
| Industry | Legal technology (LegalTech) / Artificial Intelligence |
| Credit package | AWS Activate Founders |
| Org ID | — (not applicable) |
| Current funding stage | Bootstrapped / self-funded (pre-seed). No external investment. |
| Total funding raised | USD 0 |
| Most recent funding date | Not applicable — no funding rounds |
| Revenue | None yet (pre-revenue) |
| Primary contact | Nurlan Khabibulla, Founder & CTO — dev@konsilier.com — https://www.linkedin.com/in/khabibulla |
| Second contact | Saltanat Tulegenova, CEO — saltanat@konsilier.com |
| Is the company government-owned or government-funded? | No |

**Product description (short, ~1 sentence)**
> Konsilier AI is an AI legal assistant for people and small businesses in Kazakhstan: a free AI chat explains your rights with links to official law texts, and a ready-to-file legal document can be generated for a one-time fee.

**Product description (long)**
> Konsilier AI helps people and small businesses in Kazakhstan understand and act on everyday legal problems. A free AI chat explains the user's rights and links to the official texts of Kazakh law (adilet.zan.kz). When a formal document is needed, the service generates a ready-to-file claim, complaint or application under Kazakh law for a one-time fee of 1,990 KZT; a "full case" package costs 9,990 KZT. The product launched in September 2026 as a web app, an installable PWA and a Telegram bot, with 20 published Kazakhstan scenarios. Personal data is de-identified before any text is sent to a language model. Konsilier AI is an AI tool: it does not provide lawyers and documents are drafts for the user to check before filing.

**Target market**
> Individuals and small businesses in Kazakhstan who need to understand their rights and prepare legal documents (claims, complaints, applications) without the cost of a law firm. Planned expansion through country packs for Central Asia, the Caucasus, Turkey and the MENA region.

**Current traction** (только факты, без метрик)
> Launched in September 2026: web app, installable PWA and Telegram bot are live at konsilier.com. 20 Kazakhstan legal scenarios are published. Paid document generation is live (1,990 KZT per document; 9,990 KZT full-case package). Pre-revenue; no external funding.

**How will you use AWS / Activate credits?**
> We will run Anthropic Claude through Amazon Bedrock to generate our paid legal documents. Today we pay Anthropic directly with a hard cap of USD 3 per day and USD 50 per month, which limits how many documents we can produce; our free chat runs on free-tier models. Activate credits would let us move document generation to Bedrock, lift that cap, and later scale beyond free chat models. Longer term we plan to build our own legal language model for Russian and Kazakh ("Zann") and country packs for Central Asia, the Caucasus, Turkey and MENA.

**Technical use / AWS services of interest**
> Amazon Bedrock (Anthropic Claude models) for document generation. Our application servers currently run on Yandex Cloud (Kazakhstan region).

### Дополнительно: форма Anthropic First Time Use в Bedrock (после одобрения, поля по [S7])

| Поле (API) | Ответ |
|---|---|
| companyName | Konsilier AI LLP |
| companyWebsite | https://konsilier.com |
| intendedUsers | External (1) |
| industryOption | Legal (сверить со списком в консоли) |
| useCases | Generating ready-to-file legal documents (claims, complaints, applications) under Kazakh law for individuals and small businesses in Kazakhstan, based on the user's description of their situation. Personal data is de-identified before text is sent to the model. Documents are drafts that the user reviews before filing; no lawyers are provided on the platform. |

---

## 4. Что нужно от владельца

1. **«Да» на подачу AWS Activate** и подтверждение очереди. Сейчас AWS после Astana Hub, и §2 говорит в пользу того, чтобы эту очередь сохранить.
2. **AWS-аккаунт**: кто создаёт (предлагаю Нурлана) и на какой email. Нужен ящик на домене **@konsilier.com**, чтобы домен совпал с заявкой. Предлагаю dev@konsilier.com, если он ещё не занят другим AWS-аккаунтом.
3. **Платёжная карта** для AWS-аккаунта: чья карта и в какой валюте. Для Paid plan и для покупок моделей в Marketplace нужен действующий способ оплаты [S5][S7]. Счёт ТОО есть (владелец, 30.09) — нужна корпоративная карта к нему, лучше в USD.
4. **Телефон** для верификации AWS-аккаунта: AWS обычно требует его при регистрации. **Проверить** при создании аккаунта, официального источника я не открывал.
5. **Справка о госрегистрации ТОО** (PDF, из папки Drive «Konsilier / Главные документы») — понадобится для апелляции, если AWS не сможет проверить компанию [S3, ReasonCode_12].
6. **Правки сайта** — зона сессии MVP, «Документация» передаёт их туда (сайт не меняет):
   - добавить `https://konsilier.com/robots.txt` с разрешением для краулеров — задача разработчику;
   - убрать из meta description фразу «…а когда нужно — поможет найти юриста». Она противоречит правилу «юристов на платформе нет», а AWS читает сайт;
   - в подвале исправить LinkedIn `…/company/konsilier.ai` на `…/company/konsilier/` (или сказать, какой адрес правильный).
7. **Вопрос Astana Hub** (см. §2): не отнимет ли Founders-кредит право на их AWS-перк. Задать может любой, кто ведёт переписку с Astana Hub.

---

## 5. Пошагово (после «да» владельца)

1. Разработчик исправляет сайт по п. 4.6 и проверяет: главная отдаёт 200, `robots.txt` отдаёт 200 с `Allow`, на страницах есть название «Konsilier AI».
2. Нурлан создаёт **AWS Builder ID** на dev@konsilier.com и подтверждает email [S2]. (FAQ советует для Builder ID личную почту, а страница кредитов — рабочую [S2][S3]. Рабочая безопаснее для совпадения доменов.)
3. Заполнить **профиль AWS Activate** рабочим email @konsilier.com [S2].
4. Создать **AWS-аккаунт** на тот же домен, добавить карту и **перевести аккаунт на Paid plan**: Console → Billing → «Upgrade plan» [S5]. Работать под root или IAM-админом.
5. В заявке выбрать **Activate Founders** и перенести ответы из §3.
6. **Привязать AWS-аккаунт** к Builder ID (Link my AWS account), затем нажать «Verify your account» в консоли и дождаться «Accounts linked successfully» [S2].
7. Перечитать заявку (уровень финансирования, домены) и нажать **Submit**. После отправки заявку не отредактировать [S2][S3].
8. Ждать 7–10 рабочих дней и следить за статусом на aws.amazon.com/startups/credits/status. Письма могут попасть в спам [S3].
9. После одобрения проверить в Billing → Credits сумму и **дату истечения** и поставить напоминание [S2]. Затем включить Claude в Bedrock: IAM-права Marketplace, форма Anthropic FTU (§3), выбор региона и модели [S7]. Переключение провайдера в коде и лимиты расходов — отдельной задачей разработчику с «да» владельца.
10. Записать результат в `team/decisions.md` и `team/product.md` ветки `claude/ai-team` (по CLAUDE.md).

---

## Источники

Все проверены 30.09.2026.

- [S1] AWS Activate Credits: https://aws.amazon.com/startups/credits/
- [S2] Applying for AWS Activate Credits: A step-by-step guide (AWS, 04.06.2026): https://aws.amazon.com/aws-startups/learn/applying-for-aws-activate-credits-a-step-by-step-guide/
- [S3] AWS Startups FAQ, включая тексты причин отказа: https://startups.aws.com/faq (редирект с https://aws.amazon.com/startups/faq)
- [S4] AWS Activate Terms & Conditions (Last Updated 22.01.2026), п. 1.1–1.2: https://aws.amazon.com/activate/terms/
- [S5] AWS Billing: Choosing a plan (Free vs Paid): https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/free-tier-plans.html
- [S6] AWS Promotional Credit Terms & Conditions (обновлены 24.09.2026): https://aws.amazon.com/awscredits/
- [S7] Amazon Bedrock: Request access to models: https://docs.aws.amazon.com/bedrock/latest/userguide/model-access.html
- [S8] Anthropic: Supported countries and regions: https://www.anthropic.com/supported-countries

Неофициальные для AWS источники (**проверить**):
- [N1] Astana Hub, Hub Perks (AWS Activate «up to $100,000»): https://astanahub.com/en/l/hub-perks
- [N2] Astana Hub, статья «AWS Activate, Alibaba Cloud, GOhost.kz…» (текст статьи не загрузился, условия известны только из пересказа поисковика): https://astanahub.com/en/article/aws-activate-alibaba-cloud-gohost-kz-kakie-eshche-resursy-partnerov-astana-hub-dostupny-startapam

Проверки сайта konsilier.com (30.09.2026): `/` отдаёт 200; `/robots.txt` и `/sitemap.xml` отдают 404; meta description главной содержит «поможет найти юриста»; в подвале ссылка на linkedin.com/company/konsilier.ai; в подвале есть «ТОО «Konsilier AI» · БИН 260940036818».
