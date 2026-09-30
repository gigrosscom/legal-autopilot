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
