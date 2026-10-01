# tools/zann — сбор корпуса для Zann

План обучения — [`docs/zann-llm-plan.md`](../../docs/zann-llm-plan.md). Тест и выгрузка дел — [`zann/README.md`](../../zann/README.md).

## Полный корпус на сервере — `zann-corpus`

Все действующие акты РК с old.adilet.zan.kz (≈133 тыс.) на ru и kk. Порядок: кодексы → законы → подзаконные акты →
остальное. Сбор идёт на сервере по частям, продолжается с места остановки. Тексты хранятся в хранилище приложения:
`zann/corpus/<код>.<ru|kk>.txt.gz` и `zann/corpus/manifest.jsonl.gz`. Модуль —
`apps/api/konsilier/zann/corpus.py`. Как устроен поиск актов, сколько их, сколько времени займёт сбор и как его
включить — [docs/zann-llm-plan.md, раздел 4а](../../docs/zann-llm-plan.md). Коротко:

```
ZANN_CORPUS_ENABLED=true   ZANN_CORPUS_HOUR=-1    # сразу и непрерывно (2 — только ночью 02:00–02:50)
python -m konsilier.cli zann-corpus --discover    # только найти акты (указатель портала), без текстов
python -m konsilier.cli zann-corpus --limit 50    # собрать 50 актов сейчас
```

Ход сбора — `/v1/admin/metrics` → `zann`. Тест без сети: `cd apps/api && python -m pytest tests/test_zann_corpus.py`.

Скрипт ниже нужен для быстрого локального сбора нескольких актов. Разбор страниц и вежливый загрузчик у него общие с
серверной задачей.

## collect_laws.py — официальные тексты законов РК

Скрипт берёт коды актов, на которые уже ссылаются наши сценарии в `packs/kz` (сейчас 21 акт). Для каждого он открывает
официальную страницу на old.adilet.zan.kz, то есть на том же зеркале, которое читает юридический агент
(`konsilier.lawagent.sources`). Из страницы берётся только текст акта, без меню и рекламы. Сохраняются русская и
казахская версии.

```
python tools/zann/collect_laws.py --from-packs              # все акты из packs/kz, ru и kk
python tools/zann/collect_laws.py --from-packs --limit 3    # первые 3 (самые цитируемые)
python tools/zann/collect_laws.py --codes K1500000414 Z100000274_ --langs ru
```

Результат:
- `data/zann/corpus/<код>.<ru|kk>.txt` — текст акта;
- `data/zann/manifest.jsonl` — по строке на файл: `code, title, lang, url, fetched_at, sha256, chars`.

`data/zann/` в `.gitignore`: корпус в репозиторий не попадает.

**Вежливость.** Запросы идут по одному, между ними пауза 3 секунды (`--delay`, минимум 1). User-Agent называет нас.
При ответах 429 и 5xx и при сетевых ошибках скрипт повторяет запрос с нарастающей паузой. Файлы, которые уже скачаны,
пропускаются (`--force` — скачать заново). За один запуск — до 5000 кодов. Сбор законов с adilet для Zann разрешён владельцем 30.09.2026.

**Условия.** Условия «Әділет» разрешают копировать отдельные материалы только для некоммерческого использования.
Владелец 30.09.2026 решил как юрист: тексты законов с adilet собираем для обучения Zann (вариант «В»: все кодексы,
законы и подзаконные акты). Это решение заменяет правило «Не копируем базы» в
[docs/legal-sources.md](../../docs/legal-sources.md). Robots.txt нового сайта adilet.zan.kz закрывает обучающих
ИИ-краулеров — см. docs/zann-llm-plan.md, раздел 4а.

**Тест** (без сети): `cd apps/api && python -m pytest tests/test_zann_collect_laws.py`.

## Поиск по корпусу — Zann 1 «ищет и цитирует»

Собранные акты делятся на статьи (`zann_articles`) — задача на сервере, раз в 30 минут и сразу после каждого
запуска сбора; заново режутся только новые и изменённые файлы (по sha256). Поиск — полнотекстовый PostgreSQL, без
LLM и без платных сервисов; по желанию — семантический на CPU (`ZANN_EMBEDDINGS=e5-small`). Подробно —
[docs/zann-llm-plan.md, раздел 4б](../../docs/zann-llm-plan.md).

```
cd apps/api
python -m konsilier.cli zann-index --minutes 10        # разрезать новые / изменённые акты сейчас
python -m konsilier.cli zann-search "ст. 113 ТК"       # поиск из консоли
curl -H "X-Admin-Token: …" "https://…/v1/zann/search?q=расчёт при увольнении&lang=ru&limit=5"
```

## bench_run.py — Zann-Bench на открытых моделях NVIDIA API Catalog

Открытые модели каталога (Qwen, Llama, Gemma, Nemotron; список — `--models`, что доступно — `--list-models`)
отвечают на правовые вопросы теста дважды: **с нашим поиском** (RAG: 5 статей из индекса Zann в запросе) и **без
него**. Ключ — только из переменной среды `NVIDIA_API_KEY` (в файлы и в командную строку не пишется). Бесплатный
уровень — до 40 запросов в минуту: скрипт сам держит не больше `--rpm` (максимум 40).

```
export NVIDIA_API_KEY=…                                  # ключ владельца, на сервере
python tools/zann/bench_run.py --list-models
python tools/zann/bench_run.py --bench team/zann/bench/kz-v1.jsonl \
    --index-db "$DATABASE_URL"                           # RAG + проверка «есть ли статья в корпусе»
python tools/zann/bench_run.py --bench … --models meta/llama-3.3-70b-instruct --mode norag --limit 20
python tools/zann/bench_run.py --bench … --dry-run       # без сети и ключа: фальшивая модель
```

**Формат вопроса** (`kz-v1.jsonl`, одна строка — один вопрос):

```json
{"id": "kz-qa-ru-001", "lang": "ru", "question": "…", "reference_answer": "…",
 "act": "K1500000414", "article": "113", "act_title": "Трудовой кодекс Республики Казахстан",
 "accept": [["K1500000414", "113-1"]], "verified_by": null, "source": "team", "note": ""}
```

Обязательные поля: `id, lang (ru|kk), question, reference_answer, act (код adilet), article`. `act_title` —
название акта на языке вопроса: по нему узнаётся акт в ответе модели, если нет базы индекса. `accept` — другие
верные пары (акт, статья). `verified_by` — имя юриста, проверившего эталон (пусто — не проверен).

**Что считается.** Цитата верна — ответ называет ожидаемую статью ожидаемого акта (или пару из `accept`).
Выдуманная норма — статьи нет в корпусе (с `--index-db`) или номер верный, а акт другой. Пересечение — F1 слов
ответа и эталона. Время — секунды на ответ (p50 / p95). Для режима RAG ещё — нашёл ли поиск нужную статью.

**Результат:** `docs/zann-bench-<дата>.md` (таблица модель × режим и по языкам) и сырые ответы
`data/zann/bench-<дата>.jsonl` (не в git). Тест без сети: `cd apps/api && python -m pytest tests/test_zann_bench_run.py`.
