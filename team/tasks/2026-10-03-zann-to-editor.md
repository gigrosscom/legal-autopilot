# ZANN → Редактор-лингвист: вычитка kk (семейные документы), 03.10

Юридическая суть подтверждена ZANN; прошу проверить только язык (термины, падежи, естественность). Если меняете
термин — не меняйте смысл: «свидетельство» = куәлік, «решение суда» = сот шешімі, «расторжение брака» = некені бұзу.

| ключ (packs/kz/i18n/kk.yaml → evidence) | ru | kk (черновик ZANN) |
|---|---|---|
| marriage_certificate | Свидетельство о заключении брака | Неке қию туралы куәлік |
| divorce_certificate | Свидетельство о расторжении брака или решение суда | Некені бұзу туралы куәлік не сот шешімі |
| housing_documents | Документы о жилье, где будет жить ребёнок | Бала тұратын тұрғын үйге қатысты құжаттар |
| child_references | Справки и характеристики из школы или детского сада | Мектептен не балабақшадан анықтамалар мен мінездемелер |

Также маршрут развода (packs/kz/routes.yaml, `family.divorce`, PR #242): тексты `why.kk` трёх шагов (дети есть / нет /
неизвестно). Ветка с данными документов — `claude/team-docs-by-scenario` (PR #245). Правки — коммитом в те же ветки или
списком сюда; ZANN проверит, что смысл не изменился.

## Дополнение 03.10 (ветка claude/team-route-children = #242, тоже в #245)
Новые kk-тексты (вычитать язык, смысл не менять):
- `packs/kz/i18n/kk.yaml → evidence`: title_documents, property_rights_extract, vehicle_registration, marriage_contract, valuation.
- `packs/kz/routes.yaml`: `family.property_division` и `family.personal_property` — `claim_demands.kk`, `steps[].why.kk`, `facts_ask.*.kk`, `document_title.kk`; `family.divorce` — `facts_ask.event_date.kk`.
- `packs/kz/documents/response.yaml` — title.kk «Талап арызға пікір», attachments.kk.

## Дополнение 04.10 — домен долг/подряд/труд (PR #253, ветка claude/team-debt-labor)
- `apps/api/konsilier/core/coverage/global_taxonomy.yaml` → `civil.work_payment`: title.kk, keywords.kk, examples.kk.
- `packs/kz/routes.yaml` → `civil.work_payment`: document_title.kk, claim_demands.kk, facts_ask.*.kk, steps[].label.kk / why.kk.
- `packs/kz/routing.yaml` → markers.kk для `civil.work_payment`, `labor.unpaid_wages`, `labor.dismissal`.

## Ответ 04.10 на 2026-10-03-editor-to-zann.md
Спасибо, 4 термина принимаю как есть. Три шага `family.divorce` (why.kk для children: yes / no / unknown) — ветка
`claude/team-route-children` (PR #242; та же в #245 и #253), файл `packs/kz/routes.yaml`, ключ `family.divorce`.
P1-7/P1-8 из vychitka-family-ru.md учту: в новой версии ярлык «неизвестно» уже другой (районный суд + скобка про
детей); «оңай» из текста «неизвестно» ушёл. Прочие kk-тексты — по спискам выше (семья, долг/подряд/труд).
