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

Открытые модели каталога (что реально обслуживается — `--list-models` и пробный запрос: на 01.10.2026 Qwen,
Llama 3.3/4 и Mistral отвечают 404/410) отвечают на вопросы Zann-Bench **без поиска** и **с нашим поиском** (5
статей из индекса Zann в запросе) с системным промптом чата (`konsilier/chat.py`). Ключ — только из переменной
среды `NVIDIA_API_KEY`. Бесплатный уровень — до 40 запросов в минуту: один ограничитель на процесс, считая повторы
(`--rpm`, максимум 40; два процесса сразу — делите лимит, например 10 + 30).

**Только открытая часть.** Раннер читает только строки `split == "open"`; скрытые (`hidden`) отбрасываются при
чтении и никогда не попадают в промпт, судье, сырой файл или отчёт (тест `test_hidden_items_*`).

```
python tools/zann/collect_laws.py --from-packs          # тексты актов (вежливо, 3 с между запросами)
python tools/zann/local_index.py                         # → data/zann/index.sqlite (статьи для поиска и проверки)
R="python tools/zann/bench_run.py --bench kz-v1.jsonl --index-db sqlite:///data/zann/index.sqlite"
$R --mode norag --models google/gemma-4-31b-it,nvidia/nemotron-3-ultra-550b-a55b   # ответы → data/zann/bench-<дата>.jsonl
$R --mode rag --models google/gemma-4-31b-it                                       # повторный запуск доделывает ошибки
$R --judge google/gemma-4-31b-it                         # LLM-судья: красные флаги и выдумки (отдельные колонки)
$R --report-only                                         # пересчитать оценки и записать таблицы
$R --dry-run                                             # без сети и ключа: фальшивая модель
```

**Что считается** (формат набора — `team/zann/bench/README.md`): норма (`must_cite`: акт + статья = 1, только акт =
⅓), адресат и документ (классы ключевых слов), срок (число + единица), обязательные элементы, факты, передача
юристу, язык ответа; выдуманная норма (статьи нет в корпусе, «Жилищный кодекс», право РФ) обнуляет вопрос. Отдельно —
итог с LLM-судьёй. Задержка — время самого HTTP-вызова, без очереди ограничителя. Разбивки — по категориям, типам,
языкам, сложности и `verified`.

**Результат:** таблицы `data/zann/bench-<дата>-tables.md` и сырые ответы `data/zann/bench-<дата>.jsonl` (не в
git); отчёт с выводами — `docs/zann-bench-<дата>.md`. Тест без сети: `cd apps/api && python -m pytest
tests/test_zann_bench_run.py`.
