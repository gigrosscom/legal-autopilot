# Konsilier.AI

Глобальная AI-платформа, которая превращает бытовую или деловую юридическую
проблему в готовый документ, подачу, контроль сроков и эскалацию до результата.
Первый рынок — Казахстан, но ядро ничего не знает о странах: всё страновое
лежит в `packs/<country>/` как данные.

MVP v0.1 — два сценария Казахстана:

| Сценарий | Путь |
|---|---|
| `kz.consumer.refund` — возврат денег за товар/услугу | претензия продавцу → жалоба в орган по защите прав потребителей (eOtinish) → юрист |
| `kz.money.credit_fraud` — кредит/займ, оформленный мошенниками | заявление в банк/МФО → жалоба в АРРФР → юрист |

Каналы: веб (Next.js) и Telegram-бот. Языки: русский, казахский (заготовка).

> ⚠️ Все нормы и сроки в сценариях — `TODO` до подписи юристом. Список — в
> [`packs/kz/REVIEW.md`](packs/kz/REVIEW.md). Документы до подписи помечаются «ЧЕРНОВИК».

---

## Быстрый старт

```bash
cp .env.example .env          # по умолчанию LLM_PROVIDER=mock — работает без ключа
docker compose up --build
```

| Сервис | Адрес |
|---|---|
| Веб (лендинг, дело, админка `/admin`) | http://localhost:3000 |
| API + Swagger | http://localhost:8000/docs |
| Mailpit (письма, если выбрана отправка e-mail) | http://localhost:8025 |
| S3 (SeaweedFS) | http://localhost:8333 |
| PostgreSQL | localhost:5432 (`konsilier` / `konsilier`) |

Админка: http://localhost:3000/admin, токен — `ADMIN_TOKEN` из `.env`.

Чтобы включить реальную модель: `LLM_PROVIDER=anthropic`, `ANTHROPIC_API_KEY=...`,
модели — `LLM_MODEL` (текст документа, по умолчанию `claude-sonnet-5`) и `LLM_FAST_MODEL` (классификация и извлечение данных, по умолчанию `claude-haiku-4-5`).
Claude через Amazon Bedrock (оплата из кредитов AWS, например AWS Activate): `LLM_PROVIDER=bedrock`,
`BEDROCK_REGION` (по умолчанию `eu-central-1`), `BEDROCK_ACCESS_KEY` / `BEDROCK_SECRET_KEY` (или стандартные
переменные AWS). Модели те же — префикс `anthropic.` добавляется сам; в консоли Bedrock модели нужно включить.
Telegram: создайте бота у @BotFather, укажите `TELEGRAM_BOT_TOKEN` и
`NEXT_PUBLIC_TELEGRAM_BOT` (username бота без `@`).

### Продакшен (Railway)

Проект `konsilier` в Railway: сервисы `Postgres`, `api` (том `/data` для документов) и `web`.
Оба сервиса собираются из этой ветки по Dockerfile (`RAILWAY_DOCKERFILE_PATH`) и
пересобираются на каждый пуш. Домены: `konsilier.com`, `www.konsilier.com` → `web`,
`api.konsilier.com` → `api` (CNAME на адреса, которые показывает Railway в Settings → Domains).
Секреты (`ANTHROPIC_API_KEY`, `ADMIN_TOKEN`, …) — только в Variables сервиса.

### Без Docker

```bash
# API (SQLite + локальные файлы по умолчанию)
cd apps/api && pip install -e ".[dev]"
alembic upgrade head
uvicorn --factory konsilier.main:app_factory --reload --port 8000

# Бот
cd apps/bot && pip install -e . && TELEGRAM_BOT_TOKEN=... API_URL=http://localhost:8000 \
  BOT_API_SECRET=change-me-bot python -m konsilier_bot.main

# Веб
cd apps/web && npm install && NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

Для PDF нужен LibreOffice (`soffice` в `PATH`); без него документы выдаются в DOCX.

### Тесты

```bash
cd apps/api && pytest            # 105 тестов: автомат, загрузчик, PII, e2e обоих сценариев, xx.test.dummy
cd apps/bot && pytest            # экраны бота + клиент против настоящего API
cd apps/web && npm run typecheck
# те же API-тесты на PostgreSQL:
TEST_DATABASE_URL=postgresql+psycopg://user@host/db pytest
```

---

## Архитектура

```
apps/api/konsilier/
  core/                 глобальное ядро (guard-тест запрещает в нём коды стран)
    state_machine.py    intake → qualified → action_ready → submitted → awaiting_response
                        → (resolved | escalated) → handed_to_lawyer → resolved
    scenario/           схема сценария, загрузчик с понятными ошибками, DSL условий `when`
    packs.py            JurisdictionPack / PackRegistry
    engine.py           CaseEngine — решает, что дальше (не LLM)
    ai.py               единственные вызовы LLM: квалификация, извлечение фактов,
                        «изложение обстоятельств», классификация ответа
    pii.py              ФИО/ИИН/счета → [PERSON_1]/[ID_NUMBER_1]/… до LLM и обратно
    documents.py        docxtpl → DOCX → PDF; пометка «Подготовлено с помощью ИИ» ставится ядром
    deadlines.py        DeadlineScheduler (DB + APScheduler; интерфейс под замену на Temporal)
    llm/                LLMProvider: anthropic (structured outputs), mock; RedactingLLM
    adapters/           ChannelAdapter (web, telegram), SubmissionAdapter (user_submits, email),
                        PaymentAdapter (заглушка), Storage (local, S3)
  api/                  FastAPI: /v1/cases…, /v1/admin…, /v1/packs, /v1/waitlist
apps/bot/               aiogram 3 — тонкий клиент API
apps/web/               Next.js + Tailwind — лендинг, экран дела, админка
packs/kz/               pack.yaml, scenarios/*.yaml, templates/**/*.docx, i18n/, REVIEW.md
```

Правила, которые соблюдает код:

* **AI не придумывает право.** Нормы, суммы, сроки, адресаты — только из YAML.
  Следующий шаг выбирает `CaseEngine` по условиям `when`, а не модель.
* **Заявитель — всегда пользователь.** Госорганам документы подаёт пользователь
  (инструкции из сценария); e-mail контрагенту — только по явной кнопке.
* **Пометка ИИ** добавляется ядром в тело и колонтитул каждого документа и
  выводится на экране результата; текст берётся из `pack.yaml → compliance`.
* **Персональные данные** в LLM не уходят: поля с `pii:` и шаблоны (длинные
  номера, IBAN, e-mail, телефоны) заменяются метками; словарь меток хранится
  в `cases.pii_map` в нашей БД. Фото не отправляются в LLM, пока не включён
  `EXTRACT_IMAGES_WITH_LLM` (их нельзя обезличить).
* **Одобрение юристом:** первые `APPROVAL_REQUIRED_FIRST_N` (50) дел каждого
  сценария и все дела с `needs_review` получают документ только после
  одобрения в админке.
* **Outcome** заполняется при каждом закрытии: результат, сумма, дни, шаг.
* Каждое изменение статуса пишется в `audit_log`.

### API — основной путь

```
POST /v1/users                                → token (web)   | POST /v1/users/telegram (бот)
POST /v1/cases {text, country?}               → квалификация + первый вопрос
POST /v1/cases/{id}/messages {text}           → ответ на вопрос интейка
POST /v1/cases/{id}/evidence (file, kind)     → найденные факты
POST /v1/cases/{id}/evidence/{eid}/confirm    → подтвердить факты
POST /v1/cases/{id}/actions/next              → документ следующего шага (или передача юристу)
GET  /v1/cases/{id}/actions/{aid}/document?format=pdf|docx
POST /v1/cases/{id}/actions/{aid}/submitted {via}   → срок + напоминания
POST /v1/cases/{id}/actions/{aid}/response {text | response_class | no_response}
POST /v1/cases/{id}/close {result, amount_recovered}
```

---

## Как добавить сценарий

Код ядра не меняется — это демонстрирует тест
`apps/api/tests/test_new_scenario_without_core_changes.py` со сценарием `xx.test.dummy`.

1. Создайте `packs/<cc>/scenarios/<name>.yaml`:

   ```yaml
   id: kz.money.debt_collectors      # <страна>.<домен>.<название>
   version: 0.1.0
   ontology: MONEY.DEBT.COLLECTORS
   jurisdiction: KZ
   languages: [ru, kk]
   owner: lawyer:kz-01
   reviewed_at: null                 # пока null — документы с пометкой ЧЕРНОВИК
   published: true                   # виден квалификатору
   title: {ru: …, kk: …}
   summary: {ru: …}
   classification: {keywords: {ru: [коллектор, …]}}
   claim: {type: …, amount_field: amount}
   intake:                           # вопросы задаются по одному в этом порядке
     - creditor_name
     - amount: {type: money}
     - applicant_iin: {pii: id_number, pattern: '^\d{12}$'}
     - evidence: [calls_log, messages]
   parties:
     applicant: {kind: person, name_field: applicant_name}
     respondent: {kind: business, name_field: creditor_name}
   actions:
     - id: complaint_to_collector
       title: {ru: …}
       template: kz/templates/money/collector.docx
       channel: email_or_user_submits
       addressee: {party: respondent}          # или {authority: <ключ из pack.yaml>}
       deadline: {calendar_days: 10, norm_ref: TODO}
       norm_refs: [TODO]
       demands: {ru: "…{amount} {currency}…"}
       instructions: {ru: ["…{addressee}…"]}
     - id: complaint_regulator
       when: complaint_to_collector.response in [none, refusal, partial]
       …
     - id: handoff_lawyer
       kind: handoff
       when: complaint_regulator.response != full
   pricing: {model: fixed, amount: 1990, currency: KZT}
   ```

   Условия `when`: `<action>.response ==|!= <класс>`, `in|not in [..]`, `and`, `or`.
   Классы ответа: `full`, `partial`, `refusal`, `none`, `unclear`.

2. Положите DOCX-шаблон (синтаксис docxtpl/Jinja): доступны `f.<поле>`,
   `applicant`, `addressee`, `narrative`, `demands`, `norm_refs`, `evidence`,
   `previous_actions`, `date`, `currency`. Пометку ИИ добавлять не нужно.
3. Добавьте вопросы и подписи полей в `packs/<cc>/i18n/<lang>.yaml`
   (`fields.<name>.question/label`, `evidence.<kind>`) — или прямо в поле
   сценария (`question: {ru: …}`).
4. Проверьте: `cd apps/api && python -m konsilier.cli validate` и
   `python -m konsilier.cli todos`.

## Как добавить страну

1. `packs/<cc>/pack.yaml` — `country`, `currency`, `timezone`, `languages`,
   `holidays`, `reminder_before_days`, `authorities` (органы для эскалации),
   `compliance` (пометка ИИ, дисклеймеры — обязательны для каждого языка).
2. `packs/<cc>/i18n/<lang>.yaml` — тексты интервью, ошибок, статусов, напоминаний,
   подсказки классификатору ответа (`llm_hints.response`).
3. Сценарии и шаблоны — как выше. Пакет со `status: test` не виден на лендинге и
   квалификатору без явного `country`.
4. Страна появится на лендинге как «Доступно»; до этого её выбор ведёт в лист ожидания.

---

## Что заглушено в v0.1

* **Оплата** — вручную: перевод на Kaspi по реквизитам из `.env` (`PAYMENT_MODE=manual_transfer`,
  `PAYMENT_RECIPIENT_NAME`, `PAYMENT_KASPI_PHONE`), оператор клиентского стола подтверждает его в `/ops`;
  документ готовится и скачивается после подтверждения. `PAYMENT_MODE=stub` (тесты, разработка) оплачивает сразу.
* **Голос** — нет (заготовка на уровне каналов: сообщение → текст).
* **Авторизация** — анонимный токен в браузере, Telegram ID в боте; админка по одному токену.
* **Фото** — сохраняются, но без OCR; в LLM не отправляются по умолчанию.
* **Планировщик** — APScheduler внутри процесса API; для нескольких реплик
  нужен Temporal/отдельный воркер (интерфейс `DeadlineScheduler` уже выделен).
* **Версии сценариев** — дело хранит `scenario_version`, но загружается только
  текущая версия YAML (при расхождении пишется предупреждение).
