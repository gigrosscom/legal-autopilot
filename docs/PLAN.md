# Konsilier MVP v0.1 — план

## Цель итерации

Одно дело проходит путь от первого сообщения до закрытия с `Outcome` по двум
сценариям Казахстана: `kz.consumer.refund` и `kz.money.credit_fraud`.
Каналы: web (Next.js) и Telegram. Языки: ru (полностью), kk (заготовка).

## Структура репозитория

```
apps/
  api/                      FastAPI + SQLAlchemy + Alembic (Python 3.12)
    konsilier/
      core/                 ГЛОБАЛЬНОЕ ЯДРО — ничего не знает о странах
        state_machine.py    конечный автомат дела
        scenario/           схема сценария (pydantic), загрузчик, DSL условий `when`
        packs.py            JurisdictionPack + реестр пакетов
        engine.py           CaseEngine: intake → документ → срок → ответ → следующий шаг
        interviewer.py      вопросы только по полям intake сценария
        qualifier.py        выбор сценария из опубликованных
        extraction.py       факты из текста и файлов (фото/PDF)
        pii.py              замена ИИН/ФИО/счетов метками перед LLM
        documents.py        docxtpl → DOCX → PDF (LibreOffice headless)
        deadlines.py        DeadlineScheduler (интерфейс) + DB/APScheduler реализация
        llm/                LLMProvider: anthropic, mock (heuristic), redacting-обёртка
        adapters/           ChannelAdapter, SubmissionAdapter, PaymentAdapter, Storage
      api/                  HTTP-роуты: cases, admin, packs, waitlist, users
    alembic/                миграции
    tests/                  unit + e2e (замоканный LLM, SQLite)
  bot/                      aiogram 3, общается с API по HTTP
  web/                      Next.js (App Router) + Tailwind: лендинг, чат дела, админка
packs/
  kz/                       ДАННЫЕ юрисдикции: pack.yaml, scenarios/*.yaml,
                            templates/**/*.docx, i18n/{ru,kk}.yaml, REVIEW.md
scripts/                    генерация DOCX-шаблонов, утилиты
docker-compose.yml          postgres, s3 (SeaweedFS), mailpit, api, bot, web
```

## Ключевые интерфейсы

| Интерфейс | Назначение | MVP-реализации |
|---|---|---|
| `JurisdictionPack` | страна: валюта, часовой пояс, праздники, адресаты, i18n, сценарии | загрузка из `packs/<cc>/` |
| `Scenario` | intake-поля, действия, условия `when`, сроки, цены | YAML + pydantic-валидация |
| `LLMProvider` | `complete_json(task, system, user, schema, attachments)` | `AnthropicProvider`, `MockProvider` |
| `ChannelAdapter` | уведомления пользователю | `web` (inbox в БД), `telegram` (Bot API) |
| `SubmissionAdapter` | как документ уходит адресату | `user_submits` (инструкция), `email` (SMTP) |
| `PaymentAdapter` | оплата | `StubPaymentAdapter` |
| `DeadlineScheduler` | создать срок, напоминания, `tick(now)` | `DbDeadlineScheduler` + APScheduler (заменяется на Temporal) |
| `Storage` | файлы | `LocalStorage`, `S3Storage` (MinIO) |

## Конечный автомат

```
intake → qualified → action_ready → submitted → awaiting_response
awaiting_response → resolved | escalated
escalated → action_ready | handed_to_lawyer | resolved
handed_to_lawyer → resolved
```
Любой другой переход — `InvalidTransition`. Каждый переход пишется в `AuditLog`.
`needs_review` — флаг, а не статус: дело с низкой уверенностью квалификации
идёт дальше, но все его документы требуют одобрения юриста.

## Кто что решает

* LLM: формулировка вопросов нет (тексты вопросов — данные пакета), извлечение
  значений полей из ответов/файлов, «изложение обстоятельств», классификация
  ответа контрагента (`full | partial | refusal | none | unclear`), квалификация.
* Движок: следующий шаг — только по условиям `when` из YAML. Нормы, сроки,
  суммы, адресаты — только из YAML.

## Порядок работ

1. Каркас монорепо, `.env.example`, docker-compose.
2. Ядро: автомат, схема сценария + загрузчик, пакеты, модели БД, Alembic.
3. PII, LLM-провайдеры, интервьюер, квалификатор, экстрактор.
4. Документы (docxtpl → PDF), сроки и напоминания, адаптеры.
5. HTTP API + админка (одобрение первых N дел сценария).
6. Пакет KZ: два сценария, DOCX-шаблоны, i18n, REVIEW.md.
7. Тесты: автомат, загрузчик, e2e обоих сценариев, `xx.test.dummy` без правок ядра,
   guard-тест «в ядре нет кодов стран».
8. Telegram-бот.
9. Web: лендинг, чат дела, админка.
10. README.

## Решения по умолчанию (вместо вопросов)

1. **Репозиторий.** Работаю в выданном `gigrosscom/legal-autopilot` (ветка
   `claude/zealous-volta-a3ipv6`); отдельный репозиторий `konsilier` не создаю —
   `gh` в среде нет, а создание нового репо не согласовано.
2. **Авторизация пользователей.** В MVP — анонимный токен (web) и Telegram ID
   (bot), без SMS/eGov. Админка — по `ADMIN_TOKEN`.
3. **Оплата.** Заглушка: цена из сценария показывается, счёт помечается оплаченным.
4. **Отправка email контрагенту** — адаптер есть, но по умолчанию подаёт сам
   пользователь (`user_submits`), email — только по явному выбору.
5. **Модель LLM** — `LLM_MODEL` (по умолчанию `claude-opus-5`); без
   `ANTHROPIC_API_KEY` работает `LLM_PROVIDER=mock`.
