# Кредиты на LLM-токены и GPU для Konsilier AI LLP — обзор программ

Ведёт «Документация». Поиск 30.09.2026.

Состояние на **30.09.2026**. Компания: ТОО «Konsilier AI» (Konsilier AI LLP), БИН 260940036818, зарегистрирована 29.09.2026,
Алматы; 2 сотрудника; инвестиций 0; выручки 0; сайт konsilier.com. Цель: (а) токены LLM для продукта, (б) GPU для
дообучения своей модели **Zann** на открытых весах (русский/казахский, право РК).

Правила документа:
- «проверено 30.09.2026» — страница открыта и прочитана в этот день;
- **«проверить»** — источник неофициальный (агрегатор, СМИ, зеркало), либо официальная страница не открылась (403/404/капча);
- «не опубликовано» — суммы нигде официально нет. Суммы не придуманы.
- Ничего не подано, аккаунты не создавались. Подача — только после «да» владельца по каждой программе
  (решение 30.09: очередь NVIDIA → Astana Hub (G-TON отменён 01.10) → AWS Activate → Google). Программы вне этой очереди
  (Yandex, Microsoft, Cloudflare и др.) — предложения; очередь меняет только владелец.

Подробные пакеты по Google, AWS и NVIDIA уже лежат в `team/registrations/google-startups.md`,
`team/registrations/aws-activate.md`, `team/grants/nvidia-inception.md` (ветка `claude/ai-team`); здесь — сводка.

---

## 1. Сводная таблица

Сортировка: реалистичность (Высокая → Средняя → Низкая), внутри — по объёму, доступному **нам сейчас**.
«Токены» = можно платить за API LLM; «GPU» = можно арендовать GPU для дообучения.

| # | Программа | Что реально получим сейчас | Токены | GPU | Главное условие | Реалистичность |
|---|---|---|---|---|---|---|
| 1 | Cloudflare for Startups (Tier 3) | до $10 000 кредитов, из них Workers AI — до $2 500; 1 год | Да (Workers AI: открытые модели) | Нет (только инференс) | Bootstrapped, < $1M привлечено, < 10 лет, активный LinkedIn/X/GitHub | **Высокая** — прямо для самофинансируемых |
| 2 | Microsoft for Startups (Azure startup credit offer) | $1 000 на 90 дней + $4 000 на 180 дней после верификации | Да (Azure OpenAI / Foundry) | Да (Azure GPU VM, если дадут квоту) | Без инвестора; Azure доступен в стране HQ; карта | **Высокая** — инвестор не нужен |
| 3 | Google for Startups Cloud — Start | до $2 000 на 12 мес. | Да (Gemini, Vertex AI) | Да (GPU/TPU в Google Cloud) | ≤ 24 мес., MVP, «планы привлечь VC», billing на домене | **Высокая** — уровень для pre-funded |
| 4 | AWS Activate Founders | $1 000 (до $5 000 «select participants») | Да (Bedrock, включая Claude) | Да (EC2 GPU) | Paid-план AWS, почта на домене, < 10 лет | **Высокая** — без Org ID; допуск КЗ не опубликован |
| 5 | Yandex Cloud Boost (Казахстан) | 300 000 ₸ на 180 дней (120 000 — базовые сервисы вкл. DataSphere, 180 000 — прочие) | Вероятно (AI Studio не исключён) — **проверить** | Да (DataSphere) | Резидент РК; не пользовались Yandex Cloud 180 дней | **Высокая** — программа прямо для РК |
| 6 | NVIDIA Inception | Денег нет; открывает кредиты партнёров, скидки, DLI | Косвенно | Косвенно (через партнёров) | ≥ 2 сотрудника, сайт, юрлицо, < 10 лет | **Высокая** — пакет готов, ждёт «да» |
| 7 | Alibaba Cloud Model Studio — free quota | ~1 млн токенов на каждую модель, 90 дней, автоматически | Да (Qwen и др., регион Singapore) | Нет (fine-tuning не покрыт) | Новый аккаунт | **Высокая** — но объём мал |
| 8 | Mistral — бесплатный план | $10/мес API-кредитов | Да | Нет | Аккаунт | **Высокая** — но это не стартап-программа |
| 9 | xAI — Data Sharing | $150/мес (+ стартовые, **проверить**) | Да (Grok) | Нет | ≥ $5 оплаты; согласие отдавать запросы на обучение без права отказа | **Средняя** — доступно, но несовместимо с конфиденциальностью клиентов |
| 10 | IBM — Startup with IBM | Builder: $1 000/мес на 12 мес. (**проверить**) | Да (watsonx.ai) | Да (IBM Cloud GPU, **проверить**) | Выручка < $1M, < 5 лет, не клиент IBM | **Средняя** — условия подходят, официальная страница не проверена |
| 11 | Alem.Cloud (нацсуперкомпьютер РК, H200) | Мощности GPU по заявке; тарифы «не опубликовано» | Нет | Да (H200) | Юрлицо, ЭЦП, приоритет «стратегическим» проектам | **Средняя** — лучший GPU для Zann, но цена и приоритет неясны |
| 12 | Yandex AI Studio Boost | до 1 млн ₽ на 6 мес. на AI Studio | Да | Нет данных | Цифровой продукт для внешнего рынка; страна — **проверить** | **Средняя** — условия не прочитаны (капча) |
| 13 | Alibaba Cloud AI Catalyst | до $120 000 кредитов, до 2 млрд токенов Model Studio | Да | Да | Критерии «не опубликовано»; приоритет — видео, агрегаторы, модерация | **Средняя** — открыто, но мы не в приоритетных темах |
| 14 | Google TPU Research Cloud (TRC) | Бесплатные Cloud TPU | Нет | Да (TPU) | Результаты публиковать открыто | **Средняя** — подходит, если Zann/данные будут открыты |
| 15 | DigitalOcean Hatch | Сумма «не опубликовано»; GPU — отдельная льгота | Частично | Отдельно | ≤ $10M привлечено, карта, домен | **Средняя** — bootstrapped могут подать через «Other» |
| 16 | RunPod Startup — Starter | $1 000 | Нет (свои эндпоинты) | Да | Pre-Series A с работающим продуктом; «VC strongly preferred» | **Средняя** — отбор жёсткий |
| 17 | Oracle for Startups | $500 + 70% скидка (**проверить**) | Да (OCI GenAI) | Да (GPU по квоте) | < 10 лет, MVP, не клиент OCI (**проверить**) | **Средняя** — официальная страница не открылась |
| 18 | OVHcloud Startup — Start | €10 000 на 12 мес. | Да (AI Endpoints — **проверить**) | Да (**проверить**) | Критерии и страны на странице не указаны | **Средняя** — фокус на Европу |
| 19 | Scaleway Founders | €1 000 на 1 год | Да | **проверить** | < 5 лет, < 50 чел., не клиент; фокус ЕС | **Низкая** — вероятно только ЕС |
| 20 | Anthropic — Claude for Startups | Вступить можно; кредиты — только с VC | Да (только прямой API) | Нет | Кредиты: институциональные инвестиции, < 4 лет | **Низкая** — нет инвестора |
| 21 | Lambda | Research grant до $5 000; через Inception $7 500 (**проверить**) | Нет | Да | Исследователи / участники Inception | **Низкая** сейчас, **Средняя** после Inception |
| 22 | Nebius | Кредиты только через VC-партнёров (≥ $5M); через Inception до $150 000 (**проверить**) | Да (Token Factory) | Да | VC-партнёр | **Низкая** сейчас |
| 23 | OpenAI Researcher Access | до $1 000 на 12 мес. | Да | Нет | Исследования безопасности/влияния ИИ | **Низкая** — мы коммерческий продукт |
| 24 | OpenAI for Startups (кредиты) | Только через VC-партнёров или прекращена (**проверить**) | Да | Нет | VC | **Низкая** |
| 25 | Together AI Startup Accelerator | $15 000 (Build) | Да | Да (кроме Reserved) | Уровни по сумме привлечённого | **Низкая** — funding-gated |
| 26 | Fireworks for Startups | Сумма «не опубликовано» | Да | Да (fine-tuning) | VC > $500k | **Низкая** |
| 27 | Modal for Startups | Сумма «не опубликовано» | Нет | Да | > $1M от фонда или VC-партнёр | **Низкая** |
| 28 | Cohere Labs Catalyst Grants | API-кредиты, сумма индивидуально | Да | Нет | Академия, НКО, public benefit | **Низкая** — не для компаний |
| 29 | Hugging Face | Стартап-программы на официальной странице нет | — | — | — | **Низкая** |
| 30 | Replicate | Страница /startups — 404 | — | — | — | **Низкая** |
| 31 | EuroHPC AI Factories (Playground) | GPU-часы бесплатно | Нет | Да | Только ЕС и ассоциированные страны | **Низкая** — КЗ не ассоциирована |
| 32 | ISSAI (NU) | Публичной программы GPU-доступа для стартапов нет | — | — | — | **Низкая** |
| — | Groq for Startups | **Закрыта** (≈ 05.08.2026, **проверить**); бесплатный tier остался | — | — | — | Закрыта |
| — | Nebius AI Discovery Award 2026 | **Закрыт** приём (08.05.2026), только медицина | — | — | — | Закрыта |
| — | DeepSeek | Стартап-программы нет; новым аккаунтам 5 млн токенов на 30 дней (**проверить**) | Да | Нет | — | Не программа |

---

## 2. Программы подробно

### 2.1. Cloudflare for Startups — **Высокая**
- URL: https://www.cloudflare.com/startups/ (проверено 30.09.2026).
- Даёт: Tier 3 «Bootstrapped or self-funded», «Under $1M raised» — **$10 000**; Tier 2 $100 000 и Tier 1 $350 000 — только с аффилированным инвестором. Кредиты действуют 1 год (**проверить**, из агрегатора).
- Токены: Workers AI покрыт с лимитом «$2,500 cap for Tier 3». Это инференс открытых моделей (Llama, Qwen, Mistral и др.) на Cloudflare. Можно разместить свою LoRA-версию Zann для инференса (**проверить** поддержку LoRA на Workers AI).
- GPU для обучения: нет.
- Условия: «Founded within the last 10 years», «Actively developing a technology product», «valid, publicly accessible website», «Active on LinkedIn, X (Twitter), or GitHub», впервые, бизнес-почта. Ограничений по странам на странице нет.
- Как: форма на странице; рассмотрение «typically takes up to 48 hours». Стоимость: 0.
- Почему Высокая: единственная крупная программа, где Tier прямо для bootstrapped.

### 2.2. Microsoft for Startups — **Высокая**
- URL: https://learn.microsoft.com/en-us/startups/microsoft-for-startups/mfs-faqs и https://learn.microsoft.com/en-us/startups/microsoft-for-startups/overview (проверено 30.09.2026). Подача: https://startups.microsoft.com
- Даёт без инвестора: «Azure startup credit offer: **$1,000 for 90 days**, then an additional **$4,000 for 180 days** after business verification». С кодом от Investor Network — обычно $100 000, до $150 000.
- Токены: кредиты на «eligible Azure services» — Azure OpenAI / Foundry. Покрываются ли сторонние модели Foundry (например, Claude) — **не опубликовано**, проверить в портале.
- GPU: Azure GPU-VM оплачиваются кредитами; квоты на GPU у новых подписок часто нулевые — **проверить**.
- Условия: свой софт-продукт, частная коммерческая компания, «headquartered in a country where Azure services are available», не консалтинг/агентство, не > Series B. Нужна кредитная карта. Рассмотрение ~3 рабочих дня. Отказ → повтор через 14 дней.
- Казахстан: прямого списка нет; биллинг в USD для КЗ в документах Microsoft упоминается (**проверить**).
- Почему Высокая: $5 000 без инвестора — больше, чем Google Start и AWS Founders.

### 2.3. Google for Startups Cloud Program — Start — **Высокая**
- URL: https://cloud.google.com/startup/benefits, https://cloud.google.com/startup/pre-funded, https://cloud.google.com/startup/ai (проверено 30.09.2026, подробно — `team/registrations/google-startups.md`).
- Даёт: Start — до **$2 000** на 1 год. AI-трек до $350 000 и Scale до $200 000 — только с институциональным VC (гранты и ангелы не считаются).
- Токены: Gemini/Vertex AI, Gemma. GPU/TPU: да (Vertex AI Training, Compute Engine).
- Условия: ≤ 24 мес.; MVP; «plans to seek venture funding soon» (нужно подтверждение владельца); домены почты, сайта и billing-аккаунта совпадают; нужен Cloud Billing с картой. КЗ не в списке запрещённых стран.
- Отдельно: Gemini API имеет бесплатный уровень без карты; КЗ в списке стран (https://ai.google.dev/gemini-api/docs/available-regions — **проверить**, открыт только через поиск).

### 2.4. AWS Activate Founders — **Высокая**
- URL: https://aws.amazon.com/startups/credits (проверено 30.09.2026; подробно — `team/registrations/aws-activate.md`).
- Даёт: «Up to $5,000 USD in Activate Credits» с «initial $1,000». Portfolio до $200 000 — только с Org ID от провайдера (акселератор/VC).
- Токены: Amazon Bedrock, включая сторонние модели (Claude) — по условиям Activate. GPU: EC2 (квоты — **проверить**).
- Условия: pre-Series B, < 10 лет, AWS-аккаунт на Paid plan, почта на домене компании. Допуск Казахстана официально не опубликован (в форме есть отказ «not available in your country»).
- Путь к большему: Org ID через Astana Hub или NVIDIA Inception (у Inception заявлено «до $100 000» AWS — **проверить**: https://www.thundercompute.com/blog/nvidia-inception-program-guide).

### 2.5. Yandex Cloud Boost — Казахстан — **Высокая**
- URL: https://yandex.cloud/cloud-boost/terms-main-kz (проверено 30.09.2026).
- Даёт: стандартный грант «до 300 000 тенге, включая НДС» на 180 дней; расширенный «до 1 200 000 тенге» на 60 дней и затем до 4,8 млн ₸ «при полном использовании» и после интервью.
- Структура: 120 000 ₸ — «Compute Cloud, VPC, Object Storage, Network Load Balancer, Marketplace, Monitoring, **DataSphere**, SpeechKit, Translate, Vision»; 180 000 ₸ — «иных Сервисов Платформы», кроме Interconnect. AI Studio / YandexGPT прямо не названы, но и не исключены — **проверить** у менеджера.
- GPU для Zann: DataSphere и Compute Cloud с GPU — да.
- Условия: юрлица или ИП — **резиденты РК**; нельзя, если «пользовались услугами Платформы (платно или в пробном периоде) в течение предшествующих 180 дней». Возраст и выручка не ограничены. Рассмотрение 7 дней. Стоимость: 0.
- Оговорка: данные клиентов в облаке российской компании — оценить с точки зрения репутации и хранения персональных данных (решение владельца).

### 2.6. NVIDIA Inception — **Высокая**
- URL: https://www.nvidia.com/en-us/startups/ (проверено 30.09.2026; пакет — `team/grants/nvidia-inception.md`).
- Даёт: сам денег не даёт; «free cloud credits from NVIDIA and partners», скидки, курсы DLI, Capital Connect. Суммы партнёров официально «не опубликовано»; по агрегаторам — AWS до $100 000, Nebius до $150 000 + $10 000 inference, Lambda $7 500 (всё **проверить**: https://www.thundercompute.com/blog/nvidia-inception-program-guide, https://xraise.ai/blog/lambda-startup-credits/).
- Условия: «at least one developer», сайт, юрлицо, < 10 лет; бесплатно. Уже в очереди №1.

### 2.7. Alibaba Cloud — **Высокая** (free quota) / **Средняя** (AI Catalyst)
- Free quota: https://www.alibabacloud.com/help/en/model-studio/new-free-quota (проверено 30.09.2026) — квота на каждую модель (обычно 1 000 000 токенов), 90 дней, только регион Singapore / International; не покрывает fine-tuning.
- AI Catalyst: https://www.alibabacloud.com/en/startup/ai (проверено 30.09.2026) — «Up to 2B free Model Studio tokens. Up to $120k cloud credits», POC-купоны. Требования к финансированию и странам — «не опубликовано». Приоритет: генерация видео/изображений, агрегаторы моделей, модерация. Подача онлайн, 4–5 рабочих дней.
- Qwen — одна из вероятных баз для Zann: PAI/GPU-кредиты Alibaba можно использовать для дообучения (объём — «не опубликовано»).

### 2.8. Mistral — **Высокая** (бесплатный план), стартап-программа — **Низкая**
- https://mistral.ai/pricing (проверено 30.09.2026): Free plan — «$10 /mo in API credits». Стартап-программы на странице нет. Mistralship — страница 404 по данным агрегатора (**проверить**: https://www.aicredits.co/en/blogs/mistral-startup-program).

### 2.9. xAI Data Sharing — **Средняя**
- Источники неофициальные (**проверить**): https://cloudcredits.io/providers/xai/programs/data-sharing-program, https://grok.cadn.net.cn/docs/data-sharing.html. Официальная страница docs.x.ai/docs/guides/data-sharing — 404.
- Даёт: $150/мес кредитов; нужно ≥ $5 оплат; после включения отказаться нельзя; xAI обучается на запросах и ответах. КЗ не в списке исключённых (исключены ЕС/ЕЭЗ/UK).
- Почему Средняя: запросы клиентов — это их правовые ситуации и персональные данные; передача на обучение противоречит конфиденциальности. Возможна только для обезличенных внутренних задач (например, генерация синтетических данных для Zann). Решение владельца.

### 2.10. IBM — Startup with IBM — **Средняя**
- Источники неофициальные (**проверить**): https://rihub.org/startup-with-ibm/, https://creditforstartups.com/companies/ibm; подача (по источникам) https://orders.cloud.ibm.com/IBMGEPapplication/.
- Даёт: Builder — $1 000/мес на 12 мес.; Premium — $10 000/мес. Условия: выручка < $1M, < 5 лет, не получали IBM-кредитов, не платный клиент IBM Cloud, свой домен. Инвестиции не требуются.
- Токены: watsonx.ai (Granite, Llama, Mistral). GPU/fine-tuning — **проверить**.

### 2.11. Alem.Cloud — национальный суперкомпьютер РК — **Средняя**
- Источники: https://bes.media/news/resursi-superkompyutera-stali-dostupni-dlya-yurlits-v-kazahstane/ (26.11.2025), https://www.nitec.kz/en/news/national-supercomputing-cluster-alemcloud-included-ranking-worlds-most-powerful-computing, https://primeminister.kz/en/news/digital_office/digital-headquarters-list-of-priority-it-areas-expanded-and-rules-for-alemcloud-adopted-to-implement-presidents-instructions-30618 (официальные/СМИ, прочитаны через поиск — **проверить** текущие тарифы). Платформа: https://alem-cloud.nitec.kz/
- Даёт: GPU NVIDIA H200 (64 узла HPE Cray, TOP500 №86). Доступ — юрлица, стартапы, резиденты Astana Hub. Заявка: выбрать GPU/CPU/RAM/SSD, срок, описать проект, подписать **ЭЦП юрлица** (есть). Тарифы на 11.2025 — «будут установлены позже», бесплатность «не опубликовано».
- Приоритет — «стратегически значимые» проекты ИИ; право и госуслуги прямо не названы, но есть «государственное управление», «образование». Казахская правовая модель Zann может считаться суверенным ИИ — аргумент для заявки.

### 2.12. Yandex AI Studio Boost — **Средняя**
- URL: https://yandex.cloud/ru/blog/yandex-ai-studio-boost (25.03.2026, проверено 30.09.2026); форма https://aistudio.yandex.ru/ru/boost-ai — капча, условия не прочитаны (**проверить**).
- Даёт: «гранты до 1 млн рублей» на 6 мес. на сервисы AI Studio (30+ моделей, включая DeepSeek V3.2, Qwen3-235b). Для компаний с цифровыми продуктами. Допуск КЗ — **проверить**.

### 2.13. Google TPU Research Cloud — **Средняя**
- URL: https://sites.research.google/trc/about/ (проверено 30.09.2026). Бесплатные Cloud TPU; условие — публиковать результаты (статьи, открытый код, блог). Кто может подавать — не уточнено («researchers around the world»).
- Для Zann: реально, если открыть часть результатов (например, открытый казахский правовой датасет/бенчмарк или открытая малая версия модели). Решение владельца.

### 2.14. DigitalOcean Hatch — **Средняя**
- URL: https://www.digitalocean.com/hatch (проверено 30.09.2026). Сумма — «не опубликовано» («contact your program manager»); лимит ~$10 000/мес использования. «Must have raised $10m or less»; без партнёра — выбрать «Other». Основные кредиты **не** покрывают GPU Droplets — GPU отдельной льготой.

### 2.15. RunPod Startup Program — **Средняя**
- URL: https://www.runpod.io/startup-program (проверено 30.09.2026). Starter — «$1,000 in credits» для «Pre-Series A startups with working products»; «Venture backing is strongly preferred»; «selective». Growth — только при предоплате $50 000.
- Подходит под дообучение Zann (Pods/Clusters).

### 2.16. Oracle for Startups — **Средняя**
- URL: https://www.oracle.com/startup/ — 403, не прочитано. Агрегаторы (**проверить**: https://www.startupcreds.com/programs/oracle-for-startups): $500 + 70% скидка, до $100 000 в особых случаях; < 10 лет, MVP, не клиент OCI. Квоты GPU начинаются с нуля.

### 2.17. OVHcloud / Scaleway — **Средняя / Низкая**
- OVHcloud: https://startup.ovhcloud.com/en/ (проверено 30.09.2026): Start €10 000 на 12 мес., Scale до €100 000. Критерии и страны на странице не указаны; агрегаторы: < 5 лет, < 50 чел., выручка < €10M (**проверить**: https://grantedai.com/grants/ovhcloud-startup-program-ovhcloud-c95f3514).
- Scaleway: https://www.scaleway.com/en/startup-program/ (проверено 30.09.2026): Founders €1 000/1 год; Early €9 000; Growth €36 000. «Less than 5 years», «Fewer than 50 employees», не клиент. Агрегаторы: только EU/EEA/UK/CH (**проверить**).

### 2.18. Anthropic — Claude for Startups — **Низкая**
- URL: https://claude.com/programs/startups (проверено 30.09.2026). Кредиты: «Venture backed? Apply for free credits»; условия — «equity funding from an institutional investor», «Founded within the last four years», не получали ранее. Вступить без VC можно (события, ранний доступ), но **без кредитов**. Кредиты — только на прямой API, не на Bedrock/Vertex.
- Обход: Claude через Bedrock за счёт AWS Activate (п. 2.4). КЗ в списке стран Anthropic (https://www.anthropic.com/supported-countries — **проверить**, открыт через поиск).

### 2.19. Lambda — **Низкая** (сейчас)
- https://lambda.ai/research (проверено 30.09.2026): «up to $5,000 in cloud credits» для «qualifying researchers». Стартап-оффер $7 500 для участников NVIDIA Inception — **проверить** (https://xraise.ai/blog/lambda-startup-credits/). После Inception — Средняя.

### 2.20. Nebius — **Низкая** (сейчас)
- https://nebius.com/startups (проверено 30.09.2026): «Credit offerings are currently available exclusively through our venture capital partners», минимум $5M. Research credits (https://nebius.com/nebius-research-credits-program) — только академия. AI Discovery Award 2026 — приём закрыт 08.05.2026, только медицина (https://nebius.com/ai-discovery-award). Через Inception — до $150 000 (**проверить**).

### 2.21. OpenAI — **Низкая**
- https://openai.com/startups/ — 403, не прочитано. Агрегаторы расходятся: кредиты только через VC-партнёров или программа прекращена (**проверить**: https://guptadeepak.com/startup-offers/programs/openai-for-startups).
- Researcher Access Program: до $1 000 на 12 мес., рассмотрение ежеквартально (март/июнь/сентябрь/декабрь), тема — безопасность и общественное влияние ИИ (**проверить**: https://openai.smapply.org/prog/openai_researcher_access_program/). КЗ в списке стран API (https://platform.openai.com/docs/supported-countries — **проверить**).

### 2.22. Together AI — **Низкая**
- https://www.together.ai/startup-accelerator (проверено 30.09.2026): Build ($15 000) — «Up to $5M raised»; Scale $30 000; Grow $50 000. Покрывает инференс, эндпоинты, **fine-tuning**, instant clusters (не Reserved). Можно ли с нулём привлечённого — страница не говорит; агрегаторы: «funding-gated at every tier» (**проверить**). Стоит спросить — единственная, где fine-tuning прямо в кредитах.

### 2.23. Fireworks — **Низкая**
- https://fireworks.ai/startups (проверено 30.09.2026): «Venture backed startups with >$500k in funding», < 5 лет; сумма «не опубликовано»; кредиты 1 год.

### 2.24. Modal — **Низкая**
- https://modal.com/startups (проверено 30.09.2026): Seed–Series A — VC из партнёрской сети или «>$1M from any fund»; сумма «не опубликовано»; нужна карта.

### 2.25. Cohere Labs Catalyst Grants — **Низкая**
- https://cohere.com/research/grants (проверено 30.09.2026): академия, гражданские и public-impact организации; сумма индивидуально. Коммерческое ТОО — не целевая аудитория.

### 2.26. Hugging Face — **Низкая**
- https://huggingface.co/pricing (проверено 30.09.2026): стартап-программы нет; PRO ($9/мес) — «20× included inference credits». Агрегаторы пишут о скидке на Enterprise Hub (**проверить**).

### 2.27. Replicate — **Низкая**
- https://replicate.com/startups — 404 (30.09.2026). Агрегаторы: $1 000–10 000 (**проверить**: https://guptadeepak.com/startup-offers/programs/replicate-startups).

### 2.28. Groq — **закрыта**
- Страница стартап-программы ведёт на главную (https://groq.com/groq-for-startups, 30.09.2026). По агрегатору снята 05.08.2026 (**проверить**: https://perkstack.co/blog/startup-programs-shut-down-2026). Бесплатный tier Groq остаётся и уже используется в чате.

### 2.29. DeepSeek — не программа
- Официальной стартап-программы не найдено. Новым аккаунтам ~5 млн токенов на 30 дней (**проверить**: https://yangmao.ai/en/deals/deepseek-api-free-tokens-2026/).

### 2.30. EuroHPC AI Factories — **Низкая**
- https://www.eurohpc-ju.europa.eu/playground-access-ai-factories_en (проверено 30.09.2026): Playground для SME и стартапов, доступ за 2 рабочих дня, приём постоянный. Допуск — организации из ЕС или стран, ассоциированных с Digital Europe / Horizon Europe (условия вызова: https://www.eurohpc-ju.europa.eu/document/download/f67beb2a-6a97-4f02-b6d7-017c86957867_en — прочитано через поиск, **проверить**). Казахстан не ассоциирован → нам недоступно.

### 2.31. ISSAI (Назарбаев Университет) — **Низкая**
- https://issai.nu.edu.kz/2026/02/13/issai-explains-kazllm-why-kazakhstan-built-its-own-large-language-model/ — публичной программы GPU для стартапов не найдено. Полезно другое: KazLLM (лицензия передана Astana Hub, https://nu.edu.kz/news-en/nazarbayev-university-s-issai-presents-kazakh-large-language-model-kaz-llm/) — кандидат в базовую модель для Zann; условия лицензии — **проверить**.

---

## 3. Топ-5 на эту неделю

Всё ниже — только после «да» владельца по каждой программе. Очередь 30.09 (NVIDIA → Astana Hub (G-TON отменён 01.10) → AWS → Google)
не меняю; программы 3–5 — предложение добавить в очередь.

1. **NVIDIA Inception** — пакет готов, бесплатно, КЗ не запрещён. Сам денег не даёт, но открывает партнёрские кредиты (AWS, Nebius до $150 000, Lambda) — это единственный реальный путь к крупным GPU-кредитам для Zann без инвестора.
2. **AWS Activate Founders** ($1 000, до $5 000) — кредиты тратятся на Claude в Bedrock, то есть напрямую закрывают нынешний лимит на Claude ($50/мес) примерно на 20 месяцев. Нужен Paid-аккаунт с картой.
3. **Microsoft for Startups** ($1 000 + $4 000 после верификации) — самая крупная сумма без инвестора среди больших облаков; Azure OpenAI. Сроки короткие (90 + 180 дней) — подавать, когда готовы тратить.
4. **Yandex Cloud Boost КЗ** (300 000 ₸ на 180 дней, решение за 7 дней) — программа прямо для резидентов РК, включает DataSphere с GPU: можно провести первые эксперименты по дообучению Zann. Минус — российский провайдер (решение владельца).
5. **Cloudflare for Startups Tier 3** ($10 000, из них $2 500 на Workers AI, решение за 48 ч) — для bootstrapped, быстро; даёт инференс открытых моделей (запасной бесплатный канал для чата) и хостинг сайта/хранилища.

Следом: Google Start ($2 000, уже в очереди), Alem.Cloud (H200 для Zann — сначала узнать тарифы), IBM ($12 000 за год — проверить на официальном сайте), Together AI (спросить, пускают ли с нулём инвестиций — fine-tuning прямо в кредитах).

Не тратить время сейчас: Anthropic, OpenAI, Together/Fireworks/Modal/Nebius (все требуют VC), EuroHPC (не для КЗ), Groq (закрыта), Nebius Award (закрыт, только медицина).
