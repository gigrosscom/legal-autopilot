# СПЕЦ: семейное право — данные packs/kz и тест-инвариант (пилот качества, решение владельца 03.10)

Автор значений и текстов — ZANN; связка движка и тест — Разработчик. Нормы сверены 03.10.2026 на old.adilet.zan.kz
(КоБС К1100000518, ГПК К1500000377). Скил-ревьюер: `.claude/skills/zann-family-kz/SKILL.md`.
Имена полей — предложение ZANN; Разработчик подтверждает или меняет **до** кода (одно место правды, без дублей).

## 0. Корень анти-примера «пришлите чек» (найдено 03.10)

Дела универсального пути (`kz.generic.family__*`) собираются в `core/generic.py::build_generic_scenario`: документы
дела — одно поле `evidence_kinds=("other",)`. `api/chat.py::intake_note` отбрасывает `other` → `documents_to_ask`
пуст → `documents_line` берёт `chat_documents.any` = «чек или договор, гарантийный талон или акт…». Поэтому развод и
раздел получают потребительский список. Лечится данными п. 1 + одной строкой в генераторе.

## 1. Данные (предлагаемые поля)

### 1.1 `packs/kz/routes.yaml` — у маршрута спора поле `documents` (виды из `i18n evidence.*`)
```yaml
family.divorce:          {documents: [marriage_certificate, birth_certificate, id_document]}
family.property_division:{documents: [marriage_certificate, divorce_certificate, title_documents,
                                      property_rights_extract, vehicle_registration, marriage_contract,
                                      loan_contract, valuation, birth_certificate]}
family.alimony:          {documents: [birth_certificate, marriage_certificate, divorce_certificate, pay_slip]}
family.child_residence:  {documents: [birth_certificate, housing_documents, child_references]}
```
Порядок = порядок вопроса клиенту (первые — без которых иска нет).

### 1.2 `packs/kz/i18n/{ru,kk}.yaml` → `evidence.*` — новые виды (тексты ZANN, стиль — Редактор-лингвист)
| ключ | ru |
|---|---|
| marriage_certificate | Свидетельство о браке |
| divorce_certificate | Свидетельство о расторжении брака или решение суда |
| title_documents | Договор купли-продажи, дарения или свидетельство о наследстве на имущество |
| property_rights_extract | Выписка о зарегистрированных правах на недвижимость (egov.kz) |
| vehicle_registration | Свидетельство о регистрации транспортного средства |
| marriage_contract | Брачный договор или соглашение о разделе имущества (если есть) |
| valuation | Оценка стоимости имущества (если есть) |
| housing_documents | Документы о жилье, где будет жить ребёнок |
| child_references | Справки и характеристики из школы или детского сада |
(`birth_certificate`, `loan_contract`, `pay_slip`, `id_document` — уже есть. kk — даёт ZANN после сверки терминов.)

### 1.3 `packs/kz/routes.yaml` — шаги (есть / PR)
`family.divorce` — ветки по детям (R-37, PR #242); `family.property_division` — PR #236; `family.alimony`,
`family.child_residence` — есть. Норма каждого шага — как в скиле п. 1–2.

### 1.4 `packs/kz/family.yaml` (новый, или раздел в routing.yaml — на выбор Разработчика) — константы и запреты
```yaml
alimony_shares: {one: "1/4", two: "1/3", three_plus: "1/2"}      # КоБС ст. 139 п. 1
property_division_limitation_years: 3   # КоБС ст. 37 п. 6; течёт со дня, когда узнал о нарушении (НП ВС № 5 п. 20)
court_divorce_min_wait_months: 1                                  # КоБС ст. 19 п. 3
document_titles:
  family.divorce: {ru: "Исковое заявление о расторжении брака"}
  family.property_division: {ru: "Исковое заявление о разделе общего имущества супругов"}
  family.alimony: {ru: "Исковое заявление о взыскании алиментов на содержание несовершеннолетних детей"}
  family.child_residence: {ru: "Исковое заявление об определении места жительства ребёнка"}
forbidden:           # ни в ответе чата по семейному делу, ни в документе
  ru: [чек, гарантийн, скриншот заказа, продавц, акт выполненных работ, защите прав потребителей]
  kk: [чек, кепілдік талон]
forbidden_first_step: [kz.counterparty.claim]   # досудебная претензия — не шаг семейного маршрута
```

## 2. Движок (Разработчик)
1. `build_generic_scenario`: `evidence_kinds` = `route.documents` спора, если есть, иначе `("other",)`.
2. Чат: семейное дело без списка не получает `chat_documents.any` — только список спора.
3. Документ: заголовок из `document_titles`; doc-gate проверяет `forbidden` по спорам `family.*`.

## 3. Тест-инвариант (Разработчик; значения — отсюда)
- для каждого `family.*` в `routes.yaml`: есть `documents`, все ключи есть в `evidence` ru и kk;
- `documents_to_ask` семейного дела ⊆ списка спора и не содержит слов из `forbidden`;
- первый шаг `family.*` не `kz.counterparty.claim`; у каждого шага непустая `norm`, начинается с «КоБС РК» или «ГПК РК»;
- `family.divorce`: children=yes → `kz.court.juvenile`, no → `kz.court.district` (уже в #242);
- `alimony_shares` и срок 3 года совпадают с текстом шаблонов и i18n, где упомянуты (одно место правды);
- заголовок сгенерированного документа = `document_titles[спор]`; в тексте нет `forbidden`, `[`, `TODO`.

## 4. Не механизируется — судья
Квалификация имущества (общее/личное) по фактам, основания отступить от равенства, полнота требований, тон —
`team/zann/skills/family-kz-judge.md`.

## 5. Открытые проверки (ZANN)
ГПК ст. 30 ч. 7 — закрыто 03.10 (оговорка внесена в маршрут #242 и в скил); ст. 31 ч. 1 — разъяснения ВС нет (проверено 03.10), правило ответа в скиле; начало течения 3-летнего срока ст. 37 п. 6 — закрыто 03.10: со дня, когда узнал о нарушении права (НП ВС № 5 п. 20; КС S2400000055).
