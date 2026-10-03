# Катар, Саудовская Аравия, ОАЭ, Великобритания, Канада, Австралия: сравнение с США

Версия 1 от 30.09.2026. Готовит маркетолог — креативный директор.
Задача владельца: «Исследование рынков Катара, Саудовской Аравии, ОАЭ, Великобритании, Канады и Австралии. Сравнить
по всем параметрам с США и дать рыночный анализ».

Связанные файлы: `team/strategy/us-market.md` (США — берём оттуда, заново не исследовали),
`team/strategy/big-markets.md` (модель §5.2, платёжные пути §3), `team/strategy/market-analysis.md` (первый анализ
ОАЭ, SA, QA, UK), `team/finance.md` §2 (ИИ стоит $0,07 за документ), `team/decisions.md`.

**Правило источников.** Все ссылки открыты 30.09.2026.
- Без пометки — первичный источник: текст закона, сайт суда, регулятора, статистического ведомства, прайс компании.
- **(вторичный)** — юрфирмы, блоги, агрегаторы, пресса.
- **«по выдаче поиска»** — цифра из сниппета поисковика, страницу целиком прочитать не удалось.
- **«оценка»** — расчёт или суждение команды. Баллы — экспертная оценка по приведённым данным, а не измерение.

Это не юридическое заключение. Выводы о законности — позиция команды по открытым текстам законов.
Курс на 30.09.2026 ([open.er-api.com](https://open.er-api.com/v6/latest/USD)): 1 $ = 0,756 £ = 1,419 C$ = 1,431 A$ =
3,6725 AED = 3,75 SAR = 3,64 QAR = 439,5 ₸.

---

## 0. Ответ владельцу (10 строк)

1. **Из шести стран первой берём Великобританию, а точнее Англию и Уэльс: 80 баллов против 79 у США.** Там единственный зелёный свет по закону. Legal Services Act 2007 закрепляет за юристами только 6 видов работ: выступление в суде, ведение дела, нотариат и ещё три. Письмо и иск, которые человек подаёт сам, в этот список не входят.
2. **Боль в UK подтверждена.** Иск до £10 000 подают онлайн без адвоката, пошлина — от £35. За 2025 год окружные суды получили 1,94 млн исков. Час солиситора стоит £288–579. Спрос доказан: Garfield.law продаёт досудебную претензию за £7,50.
3. **Бета UK — 01.02.2027, через 2 недели после беты Техаса.** Контент на английском общий с США. Юрлицо UK Ltd стоит £100. Пока выручка меньше £90 000 в год, НДС нет, и с документа за £4,99 чистыми остаётся около $5,7 (87 %). Если зарегистрировать НДС, останется $4,6 (70 %).
4. **Канада (65 баллов) и Австралия (63) — вторая волна, не раньше III квартала 2027 года.** Люди там платят, как в UK, а суды мелких исков удобные: в Онтарио — до C$50 000, в NCAT — потребительские споры до A$100 000. Но закон строже. В Онтарио «юридической услугой» считается уже составление документа, затрагивающего права человека. В Австралии суды считают практикой права документ, подогнанный под конкретного человека, и оговорка «мы не юристы» от этого не защищает.
5. **Поэтому в Канаду идём через регуляторную песочницу.** В Онтарио это программа LSO Access to Innovation: в ней уже 17 участников, среди них генераторы документов. В BC и Альберте есть свои песочницы. В Австралии — только с партнёром-юрфирмой. В Квебек не идём: закон требует французский язык, а у нас его нет.
6. **ОАЭ, Саудовская Аравия и Катар — красный свет.** Закон прямо отдаёт адвокатам «правовые заключения и советы» и «составление договоров» (ОАЭ — ст. 6 Закона 34/2022, Катар — Закон 23/2006). В Саудии за это грозит до 1 года тюрьмы или штраф от 30 000 SAR (ст. 37). Без лицензированного партнёра продавать документы нельзя.
7. **В Заливе много бесплатного и дешёвого.** Najiz, жалобы в MOHRE и суды мелких исков бесплатны или почти бесплатны. Shwra берёт 149 SAR за 20 минут с юристом, HAQQ и Qaanoon дают бесплатный ИИ-чат на арабском. Рынки при этом маленькие: 3 млн человек в Катаре, 11,5 млн в ОАЭ.
8. **Деньги за 12 месяцев без рекламы (база, оценка).** Выручка — $1,7–2,3 тыс. на страну, в США — $5,0 тыс. После постоянных расходов в минусе все, в Заливе — на $6–12 тыс. В плюс выходит только оптимистичный сценарий: UK +$14 тыс., CA +$16 тыс., AU +$15 тыс., США +$45 тыс.
9. **Реклама не окупается ни в одной из 7 стран.** При $200 в месяц на Google Search платящий клиент обходится в $33–133, а один платящий приносит $4,6–10,6 за 12 месяцев. Растём органикой, SEO и партнёрами, как и решено: реклама — 0 ₸.
10. **Итоговый рейтинг:** UK 80, США 79, Канада 65, Австралия 63, ОАЭ 50, Катар 49, Саудия 46. Прежний план «ОАЭ — 01.03.2027» из `market-analysis.md` предлагаем отменить: Залив — не раньше 2028 года и только с лицензированным партнёром. Первые шаги по UK — в §5.3, решение владельца — до 15.10.2026.

---

## 1. Масштаб: население, интернет, доход, язык

Источники:
- население 2025, интернет, ВВП на душу, счёт в банке — World Bank WDI через API
  ([запрос](https://api.worldbank.org/v2/country/QAT;SAU;ARE;GBR;CAN;AUS;USA/indicator/SP.POP.TOTL?format=json&mrnev=1)),
  показатели `SP.POP.TOTL`, `IT.NET.USER.ZS`, `NY.GDP.PCAP.CD`, `FX.OWN.TOTL.ZS`;
- интернет в абсолютных числах, соцсети, мобильные подключения, охват платформ — DataReportal «Digital 2026»
  ([Canada](https://datareportal.com/reports/digital-2026-canada), [Australia](https://datareportal.com/reports/digital-2026-australia),
  [UAE](https://datareportal.com/reports/digital-2026-united-arab-emirates), [Qatar](https://datareportal.com/reports/digital-2026-qatar));
  UK, SA и US — из `big-markets.md` §2 (тот же источник).

| Страна | Население, млн | Интернет, % (млн) | Соцсети, млн | Мобильные подключения, млн (% населения) | YouTube / Facebook / Instagram / TikTok 18+, млн | ВВП на душу, $ (ном.) | Счёт, % взрослых | Язык |
|---|---|---|---|---|---|---|---|---|
| **US** (ориентир) | 341,8 | 94,7 (324) | 254 | 417 (122 %) | 254 / 198 / 182 / 153 | 90 027 | 97,0 | en (es) |
| **UK** | 69,5 | 95,5 (68,1) | 55,5 | 99,3 (143 %) | 55,5 / 38,8 / 35,5 / 26,8 | 57 602 | 99,3 | en |
| **CA** | 41,7 | 94,4 (38,2) | 33,0 | 42,4 (106 %) | 33,0 / 24,6 / 21,0 / 16,6 | 55 698 | 98,4 | en, fr |
| **AU** | 27,6 | 96,1 (26,2) | 21,0 | 34,1 (126 %) | 21,0 / 17,7 / 15,2 / 10,9 | 65 130 | 98,0 | en |
| **AE** | 11,5 | 100 (11,3) | 12,5 | 23,0 (202 %) | 8,37 / 9,70 / 8,05 / 12,5 | 50 274 (2024) | 85,7 (2021) | ar, en (массово — en, хинди, урду, ru) |
| **SA** | 37,0 | 100 (34,4) | н/д | 48,7 (132 %) | 27,5 / 17,7 / 18,2 / 38,6 | 34 537 | 78,8 | ar, en |
| **QA** | 3,0 | 98,1 (3,1) | 2,95 | 4,75 (152 %) | 2,31 / 2,40 / 1,70 / 2,95 | 72 525 | 65,9 (2011) | ar, en |

**Регионы, где важно:**
- **Канада** на 01.07.2026: Онтарио — 16,26 млн, Квебек — 9,07 млн, BC — 5,71 млн, Альберта — 5,10 млн, вся страна —
  41,8 млн (StatCan, таблица 17-10-0009, [WDS API](https://www150.statcan.gc.ca/t1/wds/rest/getDataFromCubePidCoordAndLatestNPeriods)).
  Квебек — это 22 % населения, но там нужен французский (§2.2).
- **Австралия** на 31.12.2025: NSW — 8,64 млн, Victoria — 7,12 млн, Queensland — 5,71 млн, WA — 3,08 млн, вся страна —
  27,8 млн ([ABS](https://www.abs.gov.au/media-centre/media-releases/australias-population-15-december-2025)).
- **ОАЭ**: Дубай — 4,58 млн на конец 2025 года ([WAM](https://www.wam.ae/en/article/c1hd5qo-dubai-population-tops-4580-million-end-2025)),
  Абу-Даби — 4,14 млн на 2024 год ([DGE / SCAD](https://www.dge.gov.ae/en/news/2025-scad-population-update)).
  67 % жителей Абу-Даби — мужчины: страна трудовых мигрантов.
- **UK**: в Англии и Уэльсе живёт около 90 % населения, в Шотландии — около 8 % (оценка, проверить по ONS). Право и суды
  у них разные (§2.1).

**Смартфоны.** Открытых сопоставимых данных нет: GSMA Intelligence платный, DataReportal в отчётах 2026 года долю
смартфонов не даёт. Вместо неё в таблице — число мобильных подключений (SIM-карт). В Заливе оно 150–200 % от
населения: у многих по две SIM-карты.

**Вывод по масштабу.** Английский кластер UK + CA + AU — это 132 млн интернет-пользователей, в 2,5 раза меньше
США. Весь Залив — 49 млн, из них 34 млн в Саудии. По доходу на душу все шесть стран близки к «богатому» уровню,
кроме Саудии ($34,5 тыс.).

---

## 2. Карточки стран

Условные обозначения законности:
- 🟢 — наш продукт (бесплатный чат с правовой информацией и платный документ, который человек подаёт сам) прямо
  не запрещён;
- 🟡 — серая зона: нужен партнёр, песочница регулятора или заключение юриста;
- 🔴 — закон закрепляет советы и составление документов за лицензированными юристами, за нарушение грозит уголовная
  ответственность.

### 2.1 UK Великобритания

#### Англия и Уэльс — 🟢

**Боль**
- **Цена юриста.** Ориентир суда по ставкам солиситоров с 01.01.2026: категория A (стаж 8+ лет) — £288 в час
  в регионах и £579 в Лондоне. Категория C (младший юрист) — £200 и £305
  ([GOV.UK, Guideline Hourly Rates](https://www.gov.uk/guidance/solicitors-guideline-hourly-rates)).
- **Денежный иск онлайн и без адвоката.** Иск до £10 000 рассматривается по упрощённой процедуре (small claims track).
  Пошлина: до £300 — £35, £1 000–1 500 — £80, £5 000–10 000 — £455. Подача онлайн — картой
  ([GOV.UK, court fees](https://www.gov.uk/make-court-claim-for-money/court-fees)).
- **Объём.** В 2025 году окружные суды получили 1,94 млн исков, из них 1,75 млн — денежные
  ([GOV.UK, Civil Justice Statistics Q4 2025](https://www.gov.uk/government/statistics/civil-justice-statistics-quarterly-october-to-december-2025/civil-justice-statistics-quarterly-october-to-december-2025);
  цифры — из `big-markets.md`). Сервисом Resolver для бесплатных жалоб воспользовались больше 4 млн человек
  (по выдаче поиска, [resolver.co.uk/about](https://www.resolver.co.uk/about)).

**Законность без лицензии**
- **Legal Services Act 2007, s.12(1).** За юристами закреплены только 6 видов работ: (a) право выступать в суде,
  (b) ведение судебного дела (conduct of litigation), (c) оформление документов о регистрации прав (reserved
  instrument activities), (d) наследство (probate), (e) нотариат, (f) приведение к присяге
  ([legislation.gov.uk](https://www.legislation.gov.uk/ukpga/2007/29/section/12)). Правовая информация, письма и
  подготовка документа, который человек подаёт сам (litigant in person), в этот список не входят.
- **Ведение дела — это действия от имени стороны.** Апелляционный суд в деле Mazur v Charles Russell Speechlys
  ([2026] EWCA Civ 369, 31.03.2026) разрешил неюристам выполнять задачи по делу под надзором юриста
  ([judiciary.uk](https://www.judiciary.uk/judgments/mazur-and-others-v-charles-russell-speechlys-llp/); пересказ —
  [Bevan Brittan](https://www.bevanbrittan.com/insights/articles/2026/mazur-court-of-appeal-overturns-restrictions-on-conduct-of-litigation/),
  вторичный). Наш пользователь подаёт иск сам, поэтому мы дела не ведём. **Нельзя** подавать иск от имени клиента и
  переписываться с судом за него.
- **Защита потребителей.** CMA выпустила руководство для нерегулируемых юридических сервисов (завещания, онлайн-
  разводы, наследство) и открытое письмо рынку 09.10.2024
  ([GOV.UK](https://www.gov.uk/government/publications/unregulated-legal-services-consumer-protection-law-guidance)).
  Нарушения по руководству: навязанные допродажи, отказ в возврате денег, непонятная цена. С апреля 2025 года CMA
  штрафует сама (по выдаче поиска, [Pinsent Masons](https://www.pinsentmasons.com/out-law/analysis/cma-issues-guidance-unregulated-legal-service-providers-uk)).
  Нам нужны честная цена до оплаты, простой возврат и прямая надпись, что мы не юрфирма и не регулируемся SRA.
- **Позиция регуляторов по ИИ.**
  - SRA в 05.2025 впервые авторизовала ИИ-юрфирму Garfield.law
    ([sra.org.uk](https://www.sra.org.uk/garfield-ai)).
  - 17.08.2026 SRA выпустила предупреждение юристам об ошибках ИИ: за 07.2025–07.2026 поступило 42 сообщения
    (по выдаче поиска, [Law Gazette](https://www.lawgazette.co.uk/news/sra-looking-into-dozens-of-reports-of-ai-misuse/5127695.article)).
    Нас это не касается напрямую: мы не регулируемая фирма.
  - Правительство запустило «AI Growth Lab» — песочницу, первой темой которой стали legal services; участвуют SRA,
    LSB и ICO (по выдаче поиска, [Legal Futures](https://www.legalfutures.co.uk/latest-news/legal-services-lead-way-as-governments-first-ai-growth-lab)).
    Это возможность, а не обязательство.

**Персональные данные.** Применяются UK GDPR и Data Protection Act 2018. Если у нас нет юрлица в UK, нужно
назначить представителя в UK по ст. 27 UK GDPR ([ICO, territorial scope](https://ico.org.uk/media2/migrated/4031113/ic-327905-y2y5-knowledge-hub-territorial-scope.pdf)).
Если откроем UK Ltd, представитель не нужен. Требования хранить данные в UK нет. Передача данных в США (Anthropic,
Google) — по UK Extension к Data Privacy Framework или по договорным условиям ICO (проверить у юриста). Ежегодный
сбор ICO — оценка £52, проверить.

**Конкуренты**

| Сервис | Что делает | Цена | Источник |
|---|---|---|---|
| Garfield.law | ИИ-юрфирма под надзором SRA: взыскание долгов до £10 000 для малого бизнеса | Напоминание — £2, досудебная претензия — £7,50, подача иска — £50 | [sra.org.uk](https://www.sra.org.uk/garfield-ai); [LexisNexis](https://www.lexisnexis.com/en-gb/legal/news/ai-law-firm-debut-sparks-hopes-concerns) (вторичный) |
| Resolver | Бесплатные жалобы компаниям и омбудсменам | Бесплатно, 4 млн+ пользователей | по выдаче поиска |
| SortedUK | Пошаговые гайды по искам, шаблоны писем, проверка прав | Инструменты бесплатные | [sorteduk.uk](https://sorteduk.uk/small-claims-court) |
| Rocket Lawyer UK | Шаблоны документов и подписка | £34,99 в месяц после 7 бесплатных дней | по выдаче поиска, [rocketlawyer.com/gb](https://www.rocketlawyer.com/gb/en/pricing) |
| DoNotPay | Работает в UK с 2017 года (штрафы за парковку). Ухода с рынка по открытым данным не нашли | нет данных | по выдаче поиска |
| LawBite | Не проверяли | — | проверить |
| Citizens Advice, ChatGPT | Бесплатная помощь и ИИ-заменитель | 0 | — |

**Вывод по конкуренции:** 🟡. Бесплатные сервисы сильны. Платный ИИ для граждан по цене до £10 почти пустой:
Garfield работает на бизнес.

**Цена, платежи, налоги**
- Цена: **£4,99** за письмо, в тесте — £7,99 за пакет «претензия + иск» (оценка; ориентир — £7,50 у Garfield).
- Stripe UK: 1,5 % + 20p для обычных британских карт ([stripe.com/gb/pricing](https://stripe.com/gb/pricing)).
  Apple Pay и Google Pay работают через Stripe.
- VAT 20 %.
  - Иностранная компания без присутствия в UK (NETP) регистрируется с первой продажи, порога нет
    ([GOV.UK, VAT Notice 700/1](https://www.gov.uk/government/publications/vat-notice-7001-should-i-be-registered-for-vat/vat-notice-7001-should-i-be-registered-for-vat)).
  - UK Ltd получает общий порог £90 000 в год (по выдаче поиска, [gov.uk/register-for-vat](https://www.gov.uk/register-for-vat)).
  - Считается ли UK Ltd без офиса и сотрудников в UK «установленной» для VAT — **проверить у бухгалтера**.

**CAC.** Клик в Meta — £0,78–2,04. Медиана по UK за 07.2025–07.2026 — £1,18 (вторичные, разброс по источникам:
[superads.ai](https://www.superads.ai/facebook-ads-costs/cpc-cost-per-click/united-kingdom),
[adamigo.ai](https://www.adamigo.ai/blog/meta-ads-cpm-cpc-benchmarks-by-country-2026)). Поиск Google по нашим
запросам (например, «letter before action template») — оценка $2–3 за клик, проверить в Keyword Planner.

**Юнит-экономика**

| Статья | £4,99, UK Ltd, НДС не платим (до £90 000) | £4,99, НДС 20 % |
|---|---|---|
| Цена | £4,99 ($6,60) | £4,99 ($6,60) |
| НДС | 0 | −£0,83 |
| Stripe UK | −£0,30 | −£0,30 |
| ИИ | −£0,05 | −£0,05 |
| Возвраты, 3 % | −£0,15 | −£0,15 |
| Поддержка | −£0,15 | −£0,15 |
| **Нетто** | **£4,34 ≈ $5,74 (87 %)** | **£3,51 ≈ $4,64 (70 %)** |

**Вход.**
- UK Ltd — £100 онлайн с 01.02.2026, раньше было £50 (по выдаче поиска,
  [1st Formations](https://www.1stformations.co.uk/blog/companies-house-filing-fees-increase/); сверить на gov.uk).
- Нужны зарегистрированный адрес в UK (сервисы — оценка £50–150 в год) и бухгалтер (оценка £800–1 200 в год).
- Банк: Wise Business или Revolut Business для иностранного директора — проверить.
- Пак законов по официальным базам: [legislation.gov.uk](https://www.legislation.gov.uk), Pre-Action Protocol for
  Debt Claims, Consumer Rights Act 2015, формы HMCTS.
- Первые 5 сценариев:
  1. Досудебная претензия (letter before claim).
  2. Иск в Money Claim Online.
  3. Возврат депозита за аренду.
  4. Возврат денег за товар или услугу по Consumer Rights Act.
  5. Жалоба омбудсмену: финансы — FOS, энергия, связь.
- Срок — 1–2 месяца.

#### Шотландия — 🔴 для судебных бумаг, 🟡 для писем

- Иск до £5 000 рассматривается по упрощённой процедуре (simple procedure) и подаётся через портал Civil Online.
  Адвокат не обязателен. Пошлина — £20 до £300 и £112 от £300 до £5 000 (по выдаче поиска,
  [mygov.scot](https://www.mygov.scot/court-claim-money), [scotcourts.gov.uk](https://scotcourts.gov.uk/taking-action/simple-procedure/guide-to-simple-procedure)).
- **Solicitors (Scotland) Act 1980, s.32:** неюрист, который за плату (fee, gain or reward) составляет «any writ
  relating to any action or proceedings in any court», совершает преступление
  ([legislation.gov.uk](https://www.legislation.gov.uk/ukpga/1980/46/section/32/data.html)). **Платный иск для
  шотландского суда нам нельзя.** Претензии и жалобы — серая зона.
- Regulation of Legal Services (Scotland) Act 2025 (Royal Assent — 27.06.2025) вводит добровольный реестр
  нерегулируемых провайдеров и уголовную ответственность за слово «lawyer» без авторизации
  ([legislation.gov.uk](https://www.legislation.gov.uk/asp/2025/8/contents)).
- **Вывод:** Шотландия — только бесплатный чат и письма. Иски не продаём. На сайте нужен выбор «England & Wales /
  Scotland».

### 2.2 CA Канада

**Боль**
- **Цена юриста.** C$150–300 в час у младших юристов, C$250–600 в Торонто и Ванкувере (вторичный, по выдаче поиска,
  [higgertylaw.ca](https://higgertylaw.ca/blog/what-are-typical-lawyer-hourly-rates-in-canada)). Надёжного
  первичного обзора ставок нет, проверить.
- **Суды мелких исков по провинциям:**

| Провинция | Где подаётся | Лимит | Без адвоката | Источник |
|---|---|---|---|---|
| **Онтарио** | Small Claims Court | **C$50 000** с 01.10.2025 (было C$35 000), O. Reg. 42/25 | Да, типично | по выдаче поиска, [practicepro.ca](https://www.practicepro.ca/2025/10/ontario-small-claims-court-limits-increased-to-50000/) |
| **BC** | Civil Resolution Tribunal (онлайн) → Provincial Court | CRT — до C$5 000 (обязательно), суд — C$5 001–35 000 | Да, CRT задуман для самопредставления | [provincialcourt.bc.ca](https://provincialcourt.bc.ca/navigating-court-case/small-claims/claims-5000), [civilresolutionbc.ca](https://civilresolutionbc.ca/solution-explorer/small-claims/) |
| **Альберта** | Civil Claims, Court of King's Bench | До C$100 000 (оценка по памяти, проверить на albertacourts.ca) | Да | проверить |
| **Квебек** | Division des petites créances | **C$15 000** | **Адвокатов на заседание не пускают** | [courduquebec.ca](https://courduquebec.ca/en/about-the-court/jurisdiction/civil-division) |

- **Объём.** CRT в BC рассматривает около 8 800 споров в год, с 2021/22 года рост — 66 % (по выдаче поиска,
  [CRT Annual Report 2024/25](https://civilresolutionbc.ca/wp-content/uploads/CRT-Annual-Report-2024-2025.pdf)).
  Объёмы по Онтарио не нашли, проверить.

**Законность без лицензии — 🟡/🔴 по провинциям**
- **Онтарио — 🔴/🟡.**
  - Law Society Act запрещает оказывать юридические услуги без лицензии юриста или параюриста (s.26.1).
  - Юридическая услуга — это «conduct that involves the application of legal principles and legal judgment», в том
    числе выбор, составление и заполнение документов, которые затрагивают правовые интересы
    (s.1(5)–(6); пересказ — [Минюст Канады](https://www.justice.gc.ca/eng/rp-pr/jr/ecjh-eamjc/appendix-annexe.html),
    по выдаче поиска — [CanLII](https://www.canlii.org/en/on/laws/stat/rso-1990-c-l8/latest/rso-1990-c-l8.html),
    сайт не открылся). Параюристов с лицензией P1 допускают только к делам в судах и трибуналах.
  - **Выход — песочница LSO Access to Innovation (A2I).** Пилот с 10.2021. На 06.2025 одобрено 17 участников и ещё
    16 заявок на рассмотрении. Среди участников — генераторы документов для граждан: ilovelaw (шаблоны по семейному
    и трудовому праву), Jointly (брачные договоры через анкету). Участники оказали 119 848 услуг, жалоб на вред — 10
    ([LSO, отчёт Convocation, 06.2025](https://lawsocietyontario-dwd0dscmayfwh7bj.a01.azurefd.net/media/lso/media/about/convocation/2025/convocation-june-2025-futures-committee-report.pdf)).
  - LSO прямо пишет: генеративный ИИ пока не дал заметного роста продуктов для граждан. Значит, ниша свободна, но
    входить нужно через A2I.
- **BC — 🟡.** Практика права за плату закреплена за юристами. Бесплатная помощь неюристов разрешена (пересказ —
  [Минюст Канады](https://www.justice.gc.ca/eng/rp-pr/jr/ecjh-eamjc/appendix-annexe.html)). Law Society of BC ведёт
  Innovation Sandbox: участнику выдают no-action letter
  ([lawsociety.bc.ca](https://www.lawsociety.bc.ca/about-us/priorities/innovation-sandbox/about-the-innovation-sandbox/)).
  Бесплатный чат, похожий на наш (Beagle+), уже работает (см. «Конкуренты»).
- **Альберта — 🟡.** Закон не определяет «практику права». Независимые параюристы работают без регулирования в
  простых делах (пересказ — [Минюст Канады](https://www.justice.gc.ca/eng/rp-pr/jr/ecjh-eamjc/appendix-annexe.html)).
  Есть Innovation Sandbox ([lawsociety.ab.ca](https://www.lawsociety.ab.ca/law-society-of-alberta-introduces-innovation-sandbox/)).
  **Из англоязычных провинций это самая мягкая.**
- **Квебек — 🔴 для нас.** Советы дают адвокаты и нотариусы. Главное — Хартия французского языка (Bill 96): с
  01.06.2025 сайты и документы для потребителей Квебека должны быть на французском, и условия на французском не
  могут быть хуже других языков (вторичный, [CFIB](https://www.cfib-fcei.ca/en/site/qc-law-14-bill-96)). Французского
  интерфейса у нас нет.

**Персональные данные.** Федеральный закон PIPEDA — требования локализации нет. В Квебеке Law 25 требует оценку
последствий (PIA) до передачи данных за пределы провинции. Штрафы — до C$25 млн или 4 % мирового оборота (вторичный,
[BCLP](https://www.bclplaw.com/en-US/events-insights-news/quebec-law-no-25-a-little-known-privacy-law-with-a-big-reach.html)).
В BC и Альберте действуют свои законы PIPA (проверить).

**Конкуренты**

| Сервис | Что делает | Цена |
|---|---|---|
| Steps to Justice (CLEO, Онтарио) | Бесплатные пошаговые гайды | 0 |
| Clicklaw и CRT Solution Explorer (BC) | Бесплатная информация и диагностика спора | 0 |
| **Beagle+** (People's Law School, BC) | **Бесплатный ИИ-чат по праву BC** на ChatGPT. Юристы признали точными 99 % ответов. Советов не даёт ([peopleslawschool.ca](https://www.peopleslawschool.ca/about/beagle/)) | 0 |
| LawDepot (Альберта) | Шаблоны документов | C$39 в месяц или C$8,99–12,99 в месяц при оплате за год (вторичный, по выдаче поиска) |
| Участники A2I (ilovelaw, Jointly и др.) | Документы под надзором LSO | нет данных |

**Вывод:** бесплатный чат в Канаде уже есть, и его делает некоммерческая организация. Платить готовы за готовый
документ под суд.

**Цена, платежи, налоги.**
- Цена — C$9,99 ($7,04, оценка).
- Stripe CA: 2,9 % + C$0,30 ([stripe.com/ca/pricing](https://stripe.com/ca/pricing)), но только на канадское
  юрлицо. Без юрлица — через Stripe US: 2,9 % + $0,30, плюс 1,5 % за иностранную карту и 1 % за конвертацию.
- GST/HST — 5–15 % по провинции. Нерезидент регистрируется по упрощённой схеме, только когда продажи превысят
  C$30 000 за 12 месяцев ([canada.ca FAQ](https://www.canada.ca/en/revenue-agency/programs/about-canada-revenue-agency-cra/federal-government-budgets/faq-relation-electronic-commerce-supplies.html)).

**CAC.** Клик в Meta — $0,93–2,97 (вторичные, источники расходятся). Google Search — оценка C$2–4 за клик.

**Юнит-экономика (C$9,99, через Stripe US, налога нет до C$30 000).** $7,04 − комиссия $0,68 − ИИ $0,07 − возвраты
$0,21 − поддержка $0,20 = **$5,88 (84 %)**.

**Вход.**
- Юрлицо не нужно: работаем через Delaware C-corp из `us-market.md`.
- Заявка в Alberta Sandbox или LSO A2I — 3–6 месяцев (оценка).
- Партнёр-юрист провинции проверяет шаблоны (оценка C$1–3 тыс.).
- Базы законов: [CanLII](https://www.canlii.org), [e-Laws Ontario](https://www.ontario.ca/laws), [BC Laws](https://www.bclaws.gov.bc.ca).

### 2.3 AU Австралия

**Боль**
- **Цена юриста.** Ставка солиситора для госзаказчиков на 2025–26 годы — A$326,44 в час. Рыночная — A$200–880 в час
  (вторичный, по выдаче поиска, [Sprintlaw](https://sprintlaw.com.au/articles/typical-solicitor-hourly-rates-in-australia/)).
- **Трибуналы и суды мелких исков:**

| Штат | Где подаётся | Лимит | Без адвоката | Источник |
|---|---|---|---|---|
| **NSW** | NCAT, Consumer and Commercial Division | Потребительские споры до **A$100 000**, пошлина A$52–1 046 | Да | [ncat.nsw.gov.au](https://www.ncat.nsw.gov.au/case-types/consumers-and-businesses/consumer-claims.html); пошлина — по выдаче поиска |
| NSW | Local Court, Small Claims Division | До **A$20 000** | Да | [localcourt.nsw.gov.au](https://localcourt.nsw.gov.au/content/dcj/ctsd/localcourt/local-court/about-us/jurisdictions0/civil-jurisdiction.html) |
| **Victoria** | VCAT, Civil Claims List | Пошлина — A$67,40 для иска до A$15 000 (с 01.07.2026). **До A$15 000 юристов обычно не допускают** | Да | [vcat.vic.gov.au](https://www.vcat.vic.gov.au/case-types/goods-and-services/apply-goods-and-services); пошлина — вторичный |
| Queensland, WA, SA | QCAT, Magistrates Courts | Проверить | Да | проверить |

- **Объём.** Финансовый омбудсмен AFCA получил 100 745 жалоб за 2024–25 год, из них 54 581 — на банки
  ([AFCA](https://www.afca.org.au/news/media-releases/2024-25-annual-review-complaints-still-too-high)).

**Законность без лицензии — 🟡/🔴**
- **Legal Profession Uniform Law** действует в NSW, Victoria и WA. S.10(1): «An entity must not engage in legal
  practice in this jurisdiction, unless it is a qualified entity». Наказание — 250 штрафных единиц или 2 года тюрьмы.
  Деньги за такую работу возвращаются клиенту
  ([AustLII, LPUL (NSW) s.10](https://www7.austlii.edu.au/cgi-bin/viewdoc/au/legis/nsw/consol_act/lpul333/s10.html)).
  В Queensland, SA, Tasmania, ACT и NT действуют свои законы о профессии с похожим запретом (проверить).
- **Где проходит граница.** Руководство Law Society of NSW от 08.2025
  ([PDF](https://www.lawsociety.com.au/sites/default/files/2025-10/Engaging%20in%20legal%20practice%20and%20legal%20services%20under%20LPUL.pdf)):
  - суть практики права — «the advising of a particular person in a particular situation and the production of a
    document which affects legal rights, and which is tailored to the particular needs of that person»;
  - намерения и оговорка «я не юрист» значения не имеют: «Whether a person… has expressly told clients that they are
    not legal practitioner has no bearing»;
  - заполнить пустые поля в типовой форме — не юридическая услуга, а документ, собранный из фактов с анализом
    правового эффекта, — уже юридическая;
  - **правовая информация**, то есть общая, не подогнанная под конкретного человека, **законом о профессии не
    регулируется**.
- **Для нас это значит:**
  - бесплатный чат с общей информацией — 🟢;
  - заполнение официальной формы NCAT или VCAT со слов пользователя, без выбора стратегии, — 🟡;
  - претензия, которую ИИ собрал под факты человека, — 🔴/🟡.
  - Нужен партнёр — австралийская law practice. Вариант: документ формально готовит партнёр, мы — его технология
    (оценка, проверить у юриста).

**Персональные данные.** Действует Privacy Act 1988. Компании с оборотом до A$3 млн в год пока освобождены от
большинства обязанностей. Правительство согласилось отменить это исключение в принципе, но закона пока нет
(вторичный, [CoterieLabs](https://coterielabs.com.au/field-notes/privacy-act-small-business-exemption-not-removed-2026)).
Локализации нет. Для передачи данных за рубеж — APP 8.

**Конкуренты**

| Сервис | Что делает | Цена |
|---|---|---|
| LawPath | Шаблоны и ИИ-помощник, в основном для малого бизнеса | A$39 в месяц (Essentials, контракт на год), с юристом — A$139–179 в месяц (вторичный, по выдаче поиска) |
| Sprintlaw, LegalVision | Юрфирмы с фиксированной ценой для бизнеса | не проверяли |
| ClaimDone, uplaw.ai, Quillio | Помощь гражданам с заявлениями в VCAT и NCAT, по названию — ИИ | Цены не проверили (сайт не открылся) |
| Legal Aid, Community Legal Centres, гайды NCAT и VCAT | Бесплатно | 0 |

**Цена, платежи, налоги.**
- Цена — A$9,99 ($6,98, оценка).
- Stripe AU: 1,7 % + A$0,30 для австралийских карт с 01.10.2026 ([stripe.com/au/pricing](https://stripe.com/au/pricing)),
  только на юрлицо AU. Без юрлица — через Stripe US.
- GST 10 %. Нерезидент регистрируется, когда продажи превысят A$75 000 в год
  ([ATO](https://www.ato.gov.au/businesses-and-organisations/international-tax-for-business/gst-for-non-resident-businesses/how-australian-gst-works),
  по выдаче поиска).

**CAC.** Клик в Meta — $0,85–1,47 (вторичные). Google Search — оценка A$2–4.

**Юнит-экономика (через Stripe US).** $6,98 − $0,68 − $0,07 − $0,21 − $0,20 = **$5,82 (83 %)**. Если партнёр-юрфирма
берёт 30 % (оценка), остаётся $4,07.

**Вход.**
- Юрлицо не обязательно.
- Партнёр — law practice в NSW или Victoria (оценка A$2–5 тыс. на настройку и проверку).
- Базы законов: [AustLII](https://www.austlii.edu.au), [legislation.nsw.gov.au](https://legislation.nsw.gov.au),
  Australian Consumer Law (Competition and Consumer Act 2010, Sch. 2).
- Срок — 3–4 месяца.

### 2.4 AE Объединённые Арабские Эмираты

У ОАЭ три правовые зоны.
- **Материк** — Дубай, Абу-Даби, остальные эмираты. Федеральное право, суды на арабском.
- **DIFC** (Дубай) и **ADGM** (Абу-Даби) — финансовые свободные зоны со своим правом на основе английского
  common law и судами на английском. Их право действует для компаний и сделок внутри зоны, а не для обычного жителя
  Дубая.

**Боль**
- **Цена юриста.** AED 500–1 500 в час у младших, AED 1 500–3 500 у опытных. Встреча с юристом — AED 500–1 500
  (вторичный, по выдаче поиска, [hhslawyers.com](https://hhslawyers.com/blog/lawyer-cost-dubai-legal-fees/)).
- **Суды мелких исков.**
  - **Дубай, материк:** по Resolution No. 16 of 2024 суды Дубая рассматривают по упрощённой процедуре
    гражданские, коммерческие, трудовые и земельные иски до AED 1 млн (по выдаче поиска,
    [Mondaq](https://www.mondaq.com/it-and-internet/1848010/small-claims-in-the-uae-is-court-action-worth-the-cost);
    лимит проверить на dc.gov.ae — в разных источниках AED 500 000 или 1 млн).
  - **DIFC Small Claims Tribunal:** до AED 500 000, или до AED 1 млн по согласию сторон, трудовые споры — по
    согласию без лимита ([DIFC Courts, RDC Part 53](https://www.difccourts.ae/index.php/tools/pdf/court_rule?path=%2Frules-decisions%2Frules%2Fpart-53)).
    Юристы не нужны.
  - **ADGM Courts:** есть процедура мелких исков, лимит не проверили.
- **Бесплатные госканалы:** жалобы в MOHRE (трудовые), Rental Dispute Centre (аренда в Дубае), потребительская
  защита Минэкономики. Число жалоб в открытых источниках не нашли, проверить.

**Законность без лицензии — 🔴 на материке, 🟡 в DIFC и ADGM**
- **Federal Decree-Law No. 34 of 2022, ст. 6(1)** ([moj.gov.ae](https://www.moj.gov.ae/assets/d984aaa6/federal-decree-law-no-34-of-2022-regulating-the-legal-profession-and-legal-consultation-638441976591014059.aspx)):
  - «Only lawyers duly licensed in the State shall practice the legal profession or carry out any activities related
    thereto»;
  - в профессию входят «b. Giving legal opinion and advice; c. Drafting the contracts and relevant legal procedures».
- **Наказание по ст. 100:** «Whoever… practices the profession without having the professional license» — тюрьма от
  3 месяцев и/или штраф AED 30 000–100 000.
- **Ст. 101:** штраф AED 20 000–200 000 за привлечение клиентов к юристу за комиссию. Модель «приводим клиентов
  юристам за процент» тоже запрещена.
- Исполнительные правила к закону утверждены Cabinet Resolution No. 8 of 2025 в 03.2025 ([moj.gov.ae](https://www.moj.gov.ae/assets/b5a4afa2/cabinet-resolution-no-8-of-2025-regarding-the-executive-regulations-of-federal-decree-law-639105651783013992.aspx)).
  Они требуют от юридического консультанта категории A стаж 6 лет (гражданин ОАЭ) или 10 лет (иностранец)
  (по выдаче поиска).
- **Вывод:**
  - бесплатная общая информация — 🟡: прямого запрета на неё нет, но формулировки «совет» избегать;
  - платный документ под конкретного человека — 🔴 без лицензированной фирмы;
  - DIFC и ADGM лицензируют юрфирмы отдельно — 🟡, проверить. Но потребитель с материка всё равно подпадает под
    федеральный закон.
- **ИИ-политика.** ОАЭ продвигают ИИ на уровне государства (AI Strategy 2031; ИИ-платформа для законотворчества с
  04.2025, по выдаче поиска). DIFC выдаёт AI and Innovation License
  ([landing.difc.ae](https://landing.difc.ae/innovation-license-offer)). Но исключения из закона об адвокатуре для
  ИИ-сервисов мы не нашли.

**Персональные данные.** Федеральный PDPL (Federal Decree-Law 45/2021). По вторичным источникам, исполнительные
правила приняты в 2026 году, штрафы — до AED 5 млн, для передачи данных за рубеж нужна оценка
([itsecnow.com](https://itsecnow.com/regulators/pdpl-executive-regulations-2026), вторичный, **проверить на
uaelegislation.gov.ae**). В DIFC — DIFC Data Protection Law 2020, в ADGM — Data Protection Regulations 2021. Общего
требования хранить данные в ОАЭ нет, но для отдельных отраслей оно есть (проверить).

**Конкуренты**

| Сервис | Что делает | Цена |
|---|---|---|
| HAQQ | ИИ-помощник для граждан и юристов, ar и en, приложения iOS и Android | Бесплатно, платно — $33–100 в месяц |
| realLaw | ИИ для граждан ОАЭ, два языка | Бесплатно или AED 74 в месяц |
| Laiwyer.ai | Для юристов (QA, AE, SA, EG) | $49–99 в месяц |
| muhami.ae | Статьи и юрфирма | нет данных |
| MOHRE, RDC, суды | Бесплатная подача | 0 или пошлина |

Источник по HAQQ, realLaw и Laiwyer — сравнение от самой HAQQ, 22.05.2026 (вторичный, заинтересованная сторона,
[haqq.ai](https://www.haqq.ai/blog/arabic-ai-lawyer-app)).

**Цена, платежи, налоги.**
- Цена — AED 29 ($7,90).
- Stripe в ОАЭ есть: 2,9 % + AED 1 для местных карт ([stripe.com/ae/pricing](https://stripe.com/ae/pricing)).
  Счёт — только на юрлицо ОАЭ. Apple Pay есть.
- VAT 5 %. Нерезидент регистрируется с первой продажи, порога нет (вторичный,
  [PwC tax summaries](https://taxsummaries.pwc.com/united-arab-emirates/corporate/other-taxes)).

**CAC.** Клик в Meta — около $1,06, CPM вырос на 152 % за год (вторичный, по выдаче поиска). Google — оценка $1–2.

**Юнит-экономика (AED 29, Stripe AE, с лицензированным партнёром).**
- AED 29 − VAT 1,38 − Stripe 1,84 − ИИ 0,26 − возвраты 0,87 − поддержка 0,73 = AED 23,92 ≈ **$6,51 (82 %)**.
- Если партнёр забирает 30 % (оценка), остаётся **$4,56 (58 %)**.

**Вход.**
- Лицензия в свободной зоне:
  - DIFC Innovation License — около $1 500 в год плюс $100 разово (по выдаче поиска, [landing.difc.ae](https://landing.difc.ae/innovation-license-offer));
  - ADGM Tech Start-up — $1 500 в год с 01.01.2025 ([adgm.com](https://www.adgm.com/media/announcements/adgm-reduces-commercial-licence-fees-from-january-2025));
  - IFZA — от AED 10 900, Meydan — от AED 12 500 (вторичный).
- **Сама по себе лицензия свободной зоны права на правовые услуги на материке не даёт.**
- Партнёр — лицензированная юрфирма ОАЭ. Заключение юриста — оценка AED 5–15 тыс.
- Базы законов: [uaelegislation.gov.ae](https://uaelegislation.gov.ae), [difc.ae laws](https://www.difc.ae).
- Срок — 4–6 месяцев.

### 2.5 SA Саудовская Аравия — 🔴

**Боль**
- **Цена юриста.** На Shwra 20 минут с юристом, лицензированным Минюстом, стоят 149 SAR, с опытным — 499 SAR,
  50 минут со стажем 10+ лет — 999 SAR, всё с НДС ([shwra.sa](https://www.shwra.sa/en/services/LegalConsultation)).
  Shawir — от 250 SAR за 15 минут (по выдаче поиска).
- **Суды и Najiz.** Иск подаётся онлайн через портал Минюста Najiz, около 160 услуг
  (вторичный, [Lexology](https://www.lexology.com/library/detail.aspx?g=9cb2b8d5-a003-428e-ac8f-a903b812a9f6)).
  Решения по мелким искам окончательные. Трудовые иски — без пошлины (по выдаче поиска). По Закону о судебных
  расходах пошлина по другим искам — до 5 % (вторичный, [Khoshaim](https://www.khoshaim.com/blog/k-a-client-bulletin-the-judicial-costs-law)).
  Лимит для «мелких исков» в судах — проверить.
- **Объём.** Около 1,6 млн исполнительных дел по долгам домохозяйств на 165 млрд SAR (вторичный, по выдаче поиска,
  [vision2030.ai](https://vision2030.ai/analysis/saudi-household-debt-collection-cases/)). Проверить по статистике Минюста.

**Законность без лицензии — 🔴**
- **Code of Law Practice** (Royal Decree M/38, 2001, в редакции 2025 года;
  [MISA, выгрузка 29.01.2025](https://misa.gov.sa/app/uploads/2025/07/The-Code-of-Law-Practice.pdf),
  [laws.moj.gov.sa](https://laws.moj.gov.sa/en/legislation/PP5rr6HnHC8skiEH5baGkg)):
  - ст. 1: практика права — это представительство в судах, Board of Grievances и комиссиях, а также «rendering
    consultancy services based on the principles of Sharia and the rule of law». Представлять себя самого может
    каждый;
  - ст. 3: юристом может быть гражданин Саудии из реестра Минюста;
  - **ст. 37: «A term of imprisonment not exceeding one year or a minimum fine of 30,000 riyals, or both, may be
    imposed on: a) a person who… practices law in violation of the provisions of this Code».**
- ИИ-сервис с «советами» за плату — прямой риск уголовной ответственности. Работать можно только через фирму,
  лицензированную Минюстом, или как бесплатная информация.

**Персональные данные.** PDPL действует в полную силу с 14.09.2024. Передача данных за рубеж — по Regulation on
Personal Data Transfer Outside the Kingdom (редакция от 01.09.2024) и типовым договорным условиям SDAIA. Есть
Национальный реестр контролёров (вторичный, [CMS](https://cms-lawnow.com/en/ealerts/2025/09/one-year-anniversary-saudi-personal-data-protection-law)).
Жёсткой локализации для нашей отрасли не нашли, но передача данных в США требует оценки (проверить).

**Конкуренты**

| Сервис | Что делает | Цена |
|---|---|---|
| Shwra | Маркетплейс юристов, лицензированных Минюстом, 24/7, рассрочка Tamara | 149 / 499 / 999 SAR за разговор |
| Adel | ИИ-приложение на арабском | 149–199 SAR в месяц |
| Qaanoon | Бесплатный ИИ-чат на арабском | 0 |
| Thaqeel, Tashawur | Маркетплейсы лицензированных юристов | нет данных |
| Najiz и госуслуга «Legal consultations» на my.gov.sa | Госпортал | 0 |

Источники — [haqq.ai](https://www.haqq.ai/blog/arabic-ai-lawyer-app) (вторичный) и [shwra.sa](https://www.shwra.sa/en/services/LegalConsultation).

**Цена, платежи, налоги.**
- Цена — 29 SAR ($7,73).
- **Stripe в Саудии нет** ([stripe.com/global](https://stripe.com/global)). Варианты оплаты:
  - Google Play Billing — 15 %, работает с ТОО;
  - местные шлюзы (Moyasar, HyperPay, Tap) для mada, STC Pay, Apple Pay — нужен Commercial Registration в Саудии,
    проверить.
- VAT 15 %. Нерезидент регистрируется с первой продажи и назначает налогового представителя (вторичный,
  [Avalara](https://www.avalara.com/us/en/vatlive/country-guides/africa-and-middle-east/saudi-arabia/saudi-arabia-vat-on-digital-and-e-services.html)).
  Удерживает ли НДС Google Play — проверить.

**CAC.** Данных по кликам нет. Оценка — $0,5–1,5 в Google. Сильный канал — TikTok: 38,6 млн взрослых.

**Юнит-экономика (29 SAR, Google Play, партнёр 30 %).**
- 29 → без VAT 25,22 → после Google 15 % 21,43 → минус ИИ 0,26 и поддержка 0,75 = 20,42 SAR ≈ **$5,45 (70 %)**.
- С партнёром остаётся **$3,81 (49 %)**.

**Вход.**
- Лицензия MISA и регистрация: по вторичным данным, в 2026 году плата за регистрацию приостановлена, ежегодные
  платежи — около 10 000 SAR и выше (вторичный, [incorpyfy](https://incorpyfy.com/blog/ministry-of-investment-misa-license-saudi-arabia/)).
  Плюс CR, адрес, саудизация и бухгалтер: оценка $20–40 тыс. в первый год.
- Вариант без юрлица: партнёр — юрфирма, лицензированная Минюстом, продажи через Google Play. Оценка $8–12 тыс.
  (заключение, налоговый представитель, настройка).
- Базы законов: [laws.boe.gov.sa](https://laws.boe.gov.sa), [laws.moj.gov.sa](https://laws.moj.gov.sa).
- Срок — 6–12 месяцев.

### 2.6 QA Катар — 🔴

**Боль**
- **Цена юриста.** Открытых данных не нашли, проверить.
- **Суды.**
  - Приложение «Al Mahakem» Высшего судебного совета позволяет следить за делами и получать копии решений
    ([Google Play](https://play.google.com/store/apps/details?id=com.sjc.externalapp&hl=en_US)). В I квартале
    2026 года электронно зарегистрировано 777 новых дел (по выдаче поиска).
  - Qatar International Court рассматривает мелкие иски до QAR 100 000 без пошлины, онлайн
    ([qicdrc.gov.qa](https://www.qicdrc.gov.qa/courts/small-claims)). Но этот суд работает только по спорам,
    связанным с QFC, а не по спорам обычных жителей.
- **Трудовые споры.** Жалобы подаются через горячую линию, приложение Amerni и терминалы Минтруда. Если спор не
  решён, его передают в Labour Dispute Settlement Committees. Минвнутренних дел получило 5 218 жалоб от домашних
  работников за 2024 год против 1 391 за 2023 год
  ([US State Dept, Qatar 2024 Human Rights Report](https://www.state.gov/reports/2024-country-reports-on-human-rights-practices/qatar)).

**Законность — 🔴.** Law No. 23 of 2006 (в редакции Law No. 19 of 2025 от 11.09.2025) оставляет только
адвокатам представительство в судах, «giving legal opinions and advice» и «drafting contracts»
([almeezan.qa](https://www.almeezan.qa/LawView.aspx?opt=&LawID=2563&language=en); пересказ поправок —
[Sultan Al-Abdulla](https://qatarlaw.com/article/commentary-on-the-amendments-to-the-lawyers-law-issued-under-law-no-19-of-2025),
вторичный). Размер наказания за практику без лицензии не проверяли.

**Персональные данные.** PDPPL (Law No. 13 of 2016). Для передачи данных за рубеж нужна оценка, по некоторым
источникам — одобрение регулятора (вторичный, [Securiti](https://securiti.ai/qatar-personal-data-protection-law/)).
В QFC действуют свои правила о данных.

**Конкуренты.** Массового ИИ для граждан Катара не нашли. Laiwyer.ai работает для юристов. Катарцы пользуются
сервисами ОАЭ и Саудии и ChatGPT (оценка).

**Цена, платежи, налоги.**
- Цена — 29 QAR ($7,97).
- Stripe нет. Варианты: Google Play или местные QPay и NAPS (нужно юрлицо Катара, проверить).
- **НДС в Катаре нет.**

**Юнит-экономика (Google Play, партнёр 30 %).**
- 29 → после Google 24,65 → минус ИИ 0,25 и поддержка 0,73 = 23,67 QAR ≈ **$6,50 (82 %)**.
- С партнёром остаётся **$4,55 (57 %)**.

**Вход.**
- Лицензия QFC: плата за заявку снижена с $5 000 до $500 с 02.2025
  ([qfc.qa](https://www.qfc.qa/en/media-centre/news/list/qfc-application-fee-reduction-prl)). Ежегодный сбор — $5 000
  (по выдаче поиска).
- Партнёр — адвокат Катара.
- Базы законов: [almeezan.qa](https://www.almeezan.qa).
- Срок — 4–6 месяцев.

---

## 3. Сводная таблица: шесть стран против США

США — по `team/strategy/us-market.md` (Техас: Gov. Code §81.101(c), маржа $8,83, CAC $40–130, вход около $4 тыс.).

| Параметр | **US** | **UK (E&W)** | **CA** | **AU** | **AE** | **SA** | **QA** |
|---|---|---|---|---|---|---|---|
| Интернет, млн | 324 | 68,1 | 38,2 | 26,2 | 11,3 | 34,4 | 3,1 |
| ВВП на душу, $ тыс. | 90,0 | 57,6 | 55,7 | 65,1 | 50,3 | 34,5 | 72,5 |
| Час юриста | $349 | £288–579 | C$150–600* | A$200–880* | AED 500–3 500* | 149 SAR за 20 мин | н/д |
| Суд мелких исков без адвоката | Суды штатов, в Техасе justice court — до $20 тыс. (оценка, см. `us-market.md`) | До £10 000 онлайн, пошлина £35+ | ON C$50 000; BC CRT C$5 000; QC C$15 000 без адвокатов | NCAT до A$100 000; Local Court NSW A$20 000; VCAT | Суды Дубая (лимит проверить); DIFC SCT AED 500 000 | Najiz онлайн | QICDRC — только QFC |
| Объём споров | 4,7 млн исков о долгах в год | 1,94 млн исков в год | CRT ≈ 8 800 в год | AFCA 100 745 в год | н/д | ≈ 1,6 млн дел о долгах* | н/д |
| Цена документа | $9,99 | £4,99 ($6,60) | C$9,99 ($7,04) | A$9,99 ($6,98) | AED 29 ($7,90) | 29 SAR ($7,73) | 29 QAR ($7,97) |
| **Законность без лицензии** | 🟡 (🟢 TX, SC; 🔴 NY, CA) | **🟢** (Шотландия 🔴 для исков) | 🟡 AB, BC; 🔴/🟡 ON (песочница); 🔴 QC (язык) | 🟡/🔴 (только информация — 🟢) | 🔴 материк, 🟡 DIFC/ADGM | 🔴 (до 1 года тюрьмы) | 🔴 |
| Конкуренция | Очень сильная | Сильная бесплатная, платная для граждан слабая | Бесплатный ИИ Beagle+, песочница A2I | LawPath (B2B), новые ИИ-сервисы для исков | HAQQ, realLaw, бесплатные госканалы | Shwra, Adel, Qaanoon, Najiz | Слабая |
| Налог с цены | Sales tax после порогов | VAT 20 % (с UK Ltd — после £90 000) | GST/HST после C$30 000 | GST после A$75 000 | VAT 5 % с первой продажи | VAT 15 % с первой продажи | 0 |
| Платёжка | Stripe | Stripe UK | Stripe (US или CA) | Stripe (US или AU) | Stripe AE (юрлицо ОАЭ) | Google Play / локальные | Google Play / локальные |
| CAC (Google Search, $200 в месяц, оценка) | $133 | $83 | $83 | $83 | $50 | $33 | $50 |
| **Чистые с документа** | $8,83 (88 %) | $5,74 (87 %) без НДС / $4,64 (70 %) | $5,88 (84 %) | $5,82 (83 %); с партнёром $4,07 | $4,56 (58 %) с партнёром | $3,81 (49 %) с партнёром | $4,55 (57 %) с партнёром |
| Стоимость входа в 1-й год | ≈ $4 тыс. | ≈ $2 тыс. | ≈ $2,5 тыс. | ≈ $2,5 тыс. | ≈ $10 тыс. | $8–40 тыс. | ≈ $7 тыс. |
| Срок входа | 3,5 месяца (бета TX — 15.01.2027) | 1–2 месяца | 3–6 месяцев (песочница) | 3–4 месяца | 4–6 месяцев | 6–12 месяцев | 4–6 месяцев |
| Язык | en — есть | en — есть | en — есть; fr — нет | en — есть | en, ar — есть | ar — есть | en, ar — есть |

\* Вторичные источники.

### 3.1 Баллы

Каждый критерий оценивается от 0 до 5. Итог = Σ (балл ÷ 5 × вес), максимум 100. Веса: масштаб 15, боль и доступность
самостоятельной подачи 15, платёжеспособность и цена 15, **законность 20**, конкуренция 10, CAC 5, чистая маржа 10,
стоимость и срок входа 5, язык 5.

| Место | Страна | Масштаб | Боль | Цена | Законность | Конкуренция | CAC | Маржа | Вход | Язык | **Итог** |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **UK (E&W)** | 3 | 5 | 4 | 5 | 2 | 2 | 4 | 5 | 5 | **80** |
| 2 | **US** | 5 | 5 | 5 | 3 | 1 | 1 | 5 | 4 | 5 | **79** |
| 3 | CA | 3 | 4 | 4 | 2 | 3 | 2 | 4 | 4 | 4 | **65** |
| 4 | AU | 2 | 4 | 4 | 2 | 3 | 2 | 4 | 4 | 5 | **63** |
| 5 | AE | 1 | 3 | 4 | 1 | 3 | 3 | 3 | 2 | 5 | **50** |
| 6 | QA | 1 | 2 | 4 | 1 | 4 | 3 | 3 | 2 | 5 | **49** |
| 7 | SA | 2 | 3 | 3 | 1 | 2 | 3 | 3 | 1 | 4 | **46** |

**Как читать.**
- UK и США различаются на 1 балл, это в пределах точности оценки. Решает не балл, а то, что в UK не нужен выбор
  штатов и вход вдвое дешевле. У США выше потолок денег.
- CA и AU отстают на 15 и более баллов только из-за законности. Если песочница или партнёр снимут риск, они
  поднимутся до 71–73.
- Залив проигрывает по двум фактам: закон запрещает платные документы без лицензии, а рынки маленькие. Высокий
  доход этого не компенсирует.

---

## 4. Модель на 12 месяцев (оценка)

**Формула** — та же, что в `big-markets.md` §5.2, пересчитана скриптом:
- пользователи = (60 роликов в месяц × просмотры × f × 0,3 % + партнёры + SEO) × (1 + K);
- f = √(соцсети, млн ÷ 100), не больше 2. Для SA вместо соцсетей берём охват YouTube: 27,5 млн;
- сценарии «пессимистичный / базовый / оптимистичный»: просмотры в месяцы 1–3 — 800 / 3 000 / 15 000, в месяцы
  4–12 — 1 500 / 8 000 / 40 000; партнёры — 0 / 500 / 3 000 пользователей в месяц; K — 0,10 / 0,25 / 0,50; SEO —
  30 страниц × 50 / 200 / 800 визитов × 20 %;
- конверсия в оплату — 0,3 / 0,7 / 1,5 %, умноженная на поправку: US, UK, CA, AU — 1,2; AE, QA — 1,1; SA — 0,9;
- 1,2 документа на платящего, чат — $0,02 на пользователя;
- нетто с документа — из §3. В Заливе — с партнёром, который берёт 30 %;
- постоянные расходы 1-го года — строка «Стоимость входа» в §3.

**Ограничение модели.** Партнёры и SEO заданы одинаково для всех стран, поэтому для Катара (3 млн человек)
пользователи, скорее всего, завышены в 2–3 раза. Факт на 30.09.2026 — 14 пользователей в Казахстане, данных о
конверсии нет. Все цифры — допущения до первых 30 дней беты.

### 4.1 Органика, 0 $ на рекламу

| Страна | Сценарий | Пользователи | Платящие | Выручка | Маржинальный доход | **Чистыми после постоянных расходов** |
|---|---|---|---|---|---|---|
| **US** (`us-market.md`) | пессим. / **база** / оптим. | 8 тыс. / **49 тыс.** / 289 тыс. | 29 / **415** / 5 194 | $0,3 тыс. / **$5,0 тыс.** / $62 тыс. | +$0,1 тыс. / **+$3,5 тыс.** / +$49,8 тыс. | −$3,9 тыс. / **−$0,5 тыс.** / **+$45,8 тыс.** |
| **UK** | пессим. / **база** / оптим. | 5,3 тыс. / **34 тыс.** / 196 тыс. | 19 / **285** / 3 524 | $0,2 тыс. / **$2,3 тыс.** / $27,9 тыс. | $0 / **+$0,9 тыс.** / +$15,7 тыс. | −$2,0 тыс. / **−$1,1 тыс.** / **+$13,7 тыс.** |
| UK, UK Ltd без НДС ($5,74) | база / оптим. | 34 тыс. / 196 тыс. | 285 / 3 524 | $2,3 тыс. / $27,9 тыс. | +$1,3 тыс. / +$20,4 тыс. | −$0,7 тыс. / **+$18,4 тыс.** |
| **CA** | пессим. / **база** / оптим. | 4,8 тыс. / **31 тыс.** / 177 тыс. | 17 / **259** / 3 188 | $0,1 тыс. / **$2,2 тыс.** / $26,9 тыс. | $0 / **+$1,2 тыс.** / +$19,0 тыс. | −$2,5 тыс. / **−$1,3 тыс.** / **+$16,5 тыс.** |
| **AU** (без партнёра) | пессим. / **база** / оптим. | 4,4 тыс. / **29 тыс.** / 164 тыс. | 16 / **241** / 2 959 | $0,1 тыс. / **$2,0 тыс.** / $24,8 тыс. | $0 / **+$1,1 тыс.** / +$17,4 тыс. | −$2,5 тыс. / **−$1,4 тыс.** / **+$14,9 тыс.** |
| **AE** (партнёр) | пессим. / **база** / оптим. | 4,1 тыс. / **27 тыс.** / 153 тыс. | 13 / **207** / 2 524 | $0,1 тыс. / **$2,0 тыс.** / $23,9 тыс. | $0 / **+$0,6 тыс.** / +$10,8 тыс. | −$10,0 тыс. / **−$9,4 тыс.** / +$0,8 тыс. |
| **SA** (партнёр) | пессим. / **база** / оптим. | 4,6 тыс. / **30 тыс.** / 172 тыс. | 12 / **189** / 2 317 | $0,1 тыс. / **$1,7 тыс.** / $21,5 тыс. | $0 / **+$0,3 тыс.** / +$7,2 тыс. | −$12,0 тыс. / **−$11,7 тыс.** / −$4,8 тыс. |
| **QA** (партнёр) | пессим. / **база** / оптим. | 3,5 тыс. / **24 тыс.** / 133 тыс. | 12 / **181** / 2 196 | $0,1 тыс. / **$1,7 тыс.** / $21,0 тыс. | $0 / **+$0,5 тыс.** / +$9,3 тыс. | −$7,0 тыс. / **−$6,5 тыс.** / +$2,3 тыс. |

Для AU с партнёром ($4,07) базовый маржинальный доход ≈ +$0,6 тыс., чистыми — около −$1,9 тыс.

### 4.2 Минимальный бюджет: $200 в месяц на поиск Google (по запросам с явным намерением)

Допущения: CPC по §3 (оценка), конверсия «клик → оплата» — 3 %, 1,2 документа на платящего.

| Страна | Клики за год | Платящие | Выручка | Вклад после $2 400 рекламы | CAC платящего |
|---|---|---|---|---|---|
| US | 600 | 18 | $216 | −$2 221 | $133 |
| UK | 960 | 29 | $228 | −$2 259 | $83 |
| CA | 960 | 29 | $243 | −$2 216 | $83 |
| AU | 960 | 29 | $241 | −$2 218 | $83 |
| AE | 1 600 | 48 | $455 | −$2 169 | $50 |
| SA | 2 400 | 72 | $668 | −$2 119 | $33 |
| QA | 1 600 | 48 | $459 | −$2 170 | $50 |

**Вывод.** Один платящий приносит за 12 месяцев $4,6–10,6. Реклама окупается, только если платящий обходится
дешевле этой суммы, а такого нет ни в одной стране. Бюджет стоит тратить только на проверку CPC и конверсии: до $100
на страну и после «да» владельца.

### 4.3 Английский кластер вместе

- Если один поток роликов и SEO на английском работает на US, UK, CA и AU сразу, в базовом сценарии это около
  143 тыс. пользователей и $11,5 тыс. выручки за 12 месяцев. Маржинальный доход — около $6,7 тыс., постоянные
  расходы — около $11 тыс.
- В оптимистичном сценарии — 0,83 млн пользователей, $142 тыс. выручки и около +$90 тыс. чистыми.
- Добавить UK к США почти ничего не стоит: $2 тыс. и один пак законов. Поэтому UK — первый кандидат.

---

## 5. Вывод

### 5.1 Рейтинг семи стран

| Место | Страна | Баллы | Роль | Решение |
|---|---|---|---|---|
| 1 | **Великобритания (Англия и Уэльс)** | 80 | Первая страна из этой группы. Легальный вход без лицензии | **Бета 01.02.2027** |
| 2 | США | 79 | Главные деньги (план `us-market.md`: бета TX — 15.01.2027) | По плану `us-market.md` |
| 3 | Канада (Альберта, BC; Онтарио — через A2I) | 65 | Вторая волна английского кластера | Заявка в песочницу — I квартал 2027, запуск — не раньше III квартала 2027 |
| 4 | Австралия (NSW, Victoria) | 63 | Вторая волна, только с партнёром-юрфирмой | Поиск партнёра — II квартал 2027, запуск — IV квартал 2027 |
| 5 | ОАЭ | 50 | Только с лицензированной фирмой ОАЭ | Отложить до 2028 года. Бесплатный чат на ar/en можно оставить |
| 6 | Катар | 49 | Мал и закрыт законом | Отложить. Если войдём в ОАЭ, добавить Катар вместе с ним |
| 7 | Саудовская Аравия | 46 | Закрыт законом, дорогой вход, сильные местные игроки | Отложить. Возвращаться, только если появится партнёр, лицензированный Минюстом |

### 5.2 Почему Великобритания первая

1. **Единственный зелёный свет.** Наш продукт не попадает в зарезервированные виды работ по LSA 2007 s.12. Решение
   Mazur (31.03.2026) подтверждает: ведение дела — это действия от имени стороны, а у нас человек подаёт иск сам.
2. **Продукт совпадает с процедурой.** Money Claim Online и досудебная претензия по Pre-Action Protocol — стандарт,
   который граждане проходят сами.
3. **Дёшево и быстро.** UK Ltd стоит £100, Stripe UK — 1,5 % + 20p, английский интерфейс готов, контент общий с США.
4. **Маржа высокая.** $5,74 с документа за £4,99, пока нет НДС (до £90 000), или $4,64 с НДС.
5. **Спрос доказан:** Garfield.law берёт £7,50 за претензию, но работает на бизнес. Ниша «гражданин против
   компании или арендодателя» свободна от платных ИИ-игроков.

**Риски UK.**
- Бесплатные сервисы (Resolver, Citizens Advice, SortedUK) снижают конверсию.
- Правила CMA для нерегулируемых сервисов: прозрачная цена, возврат, без давления.
- Шотландия — только письма, иски туда не продаём (s.32).

### 5.3 Первые шаги по UK (даты — предложение, нужно «да» владельца)

| Дата | Шаг | Кто |
|---|---|---|
| до 15.10.2026 | Решение владельца: UK E&W как первая страна группы; цена £4,99 (тест £7,99); UK Ltd или без юрлица | Владелец |
| до 31.10.2026 | Бухгалтер UK: будет ли UK Ltd без офиса «установленной» для VAT (порог £90 000)? Нужен ли представитель по ст. 27 UK GDPR? | Финансист |
| до 15.11.2026 | UK Ltd (£100) и адрес; Stripe UK; условия сервиса и privacy для UK; оговорка «мы не юрфирма и не регулируемся SRA»; выбор «England & Wales / Scotland» | Владелец, продукт |
| до 15.12.2026 | Пак E&W из 5 сценариев по legislation.gov.uk и формам HMCTS (§2.1). Каждая норма — со ссылкой | ИИ-агенты |
| до 15.01.2027 | Проверка шаблонов солиситором E&W — желательна, оценка £500–1 500. 20 SEO-страниц («letter before action», «money claim online how to», «deposit not returned») | Владелец, маркетолог |
| **01.02.2027** | **Закрытая бета UK**: органика, общие с США ролики на английском, партнёры — студенческие юридические клиники, группы арендаторов | Команда |
| 01.03.2027 | Итог 30 дней: цель — 2 000 пользователей и конверсия ≥ 0,8 % (оценка). По итогам — решение о Канаде (песочница) и Австралии (партнёр) | Владелец |

### 5.4 Что отложить и почему

- **ОАЭ.** Ст. 6 и ст. 100 Закона 34/2022 закрепляют советы и составление документов за лицензированными юристами,
  нарушение — уголовное. Лицензия свободной зоны правовые услуги на материке не открывает. Рынок 11,5 млн, из них
  много трудовых мигрантов с низким доходом (оценка). **Это меняет план `market-analysis.md` §5 (ОАЭ —
  01.03.2027): предлагаем отменить эту дату.**
- **Саудовская Аравия.** Ст. 37 Code of Law Practice — до 1 года тюрьмы или штраф от 30 000 SAR. Stripe нет, НДС
  15 % с первой продажи, лицензия MISA дорогая. Местные сервисы уже дают 20 минут с юристом за 149 SAR и бесплатный
  ИИ-чат (Qaanoon).
- **Катар.** Закон 23/2006 запрещает советы неюристам, рынок — 3 млн человек.
- **Квебек.** Нужен французский язык (Bill 96), адвокатов в суд мелких исков не пускают, продукт придётся
  переделывать.
- **Шотландия.** Платные судебные бумаги запрещены s.32.

**Что можно в Заливе сейчас без риска.** Интерфейс ar и en уже есть. Бесплатный чат с общей правовой информацией
по ОАЭ и Саудии («куда жаловаться, какие сроки, какие госпорталы») работает без продажи документов. Это набор
аудитории до появления партнёра. Формулировки должны быть «информация», а не «совет» (оценка, проверить у местного
юриста).

---

## 6. Что проверить

| # | Вопрос | Кто | Срок |
|---|---|---|---|
| 1 | Порог VAT для UK Ltd без реального присутствия; представитель по ст. 27 UK GDPR; сбор ICO | Финансист + бухгалтер UK | 31.10.2026 |
| 2 | Лимит мелких исков в Альберте и порядок в Queensland и WA | Маркетолог | 31.10.2026 |
| 3 | Точный текст Law Society Act (Онтарио) s.1(5)–(6) — CanLII не открылся; условия участия в A2I и Alberta Sandbox | Маркетолог | 15.11.2026 |
| 4 | Лимит Small Claims Tribunal судов Дубая (AED 500 000 или 1 млн, Resolution 16/2024); процедура мелких исков ADGM | Маркетолог | 15.11.2026 |
| 5 | Исполнительные правила UAE PDPL 2026 — первичный текст на uaelegislation.gov.ae | Маркетолог | 15.11.2026 |
| 6 | CPC в Google Keyword Planner по 20 запросам на страну | Маркетолог | 31.10.2026 |
| 7 | Удерживает ли Google Play VAT в SA и AE; комиссия Play в UK с 30.06.2026 | Финансист | 31.10.2026 |
| 8 | Цены ClaimDone, uplaw.ai (AU), LawBite (UK) | Маркетолог | 31.10.2026 |
| 9 | Размер наказания в Катаре за практику без лицензии (Закон 23/2006, almeezan.qa) | Маркетолог | 30.11.2026 |
| 10 | Пересчитать модель §4 по фактам первых 30 дней беты UK и TX | Маркетолог + финансист | 01.03.2027 |
