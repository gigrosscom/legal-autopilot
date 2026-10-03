# Пилот «Курьер» — договорённость об API (Разработчик ↔ Интегратор)

Обновлено: 01.10.2026. Предложил Разработчик (интерфейс, ветка `claude/team-courier-ui`). Бэкенд — Интегратор
(ветка `claude/team-courier`). Решение владельца — `team/decisions.md` от 01.10 (3 990 ₸, Алматы, 20 доставок);
юридические тексты — `team/zann/lawyer/courier-delivery-legal.md`. **Интегратор: если что-то в форме ответа неудобно —
поправьте этот файл и напишите строку в «Пересечения» в `team/sessions.md`; интерфейс подстроится.**

Интерфейс уже собран под этот формат (данные в скриншотах — подставные, через перехват запросов в Playwright).
Поля, отмеченные «(необяз.)», интерфейс переживает без них.

## Клиент (токен клиента, как у `/v1/cases/{id}/lawyers`)

### `GET /v1/cases/{case_id}/courier`
```json
{
  "available": true,            // показать карточку «Доставить курьером»
  "reason": null,               // если false: "not_paid" | "addressee_not_supported" (госорган, суд, полиция) | "city" | "pilot_full"
  "price": 3990, "currency": "KZT", "city": "Алматы",
  "respondent": {"name": "ТОО «Ромашка»", "address": "г. Алматы, пр. Достык, 10"},   // из документа (адресат action)
  "pickup": {"address": "г. Алматы, ул. Сейдимбек, 222", "phone": "+7 701 000 00 00"}, // из данных заявителя (необяз.)
  "slots": [ {"date": "2026-10-03", "windows": [{"id": "10-13", "label": "10:00–13:00"}, {"id": "13-16", "label": "13:00–16:00"}, {"id": "16-19", "label": "16:00–19:00"}]} ],
  "order": null                 // или Order (ниже) — открытый заказ по делу
}
```

### `POST /v1/cases/{case_id}/courier` — заказ, сразу со счётом
Тело:
```json
{"pickup_address": "...", "pickup_date": "2026-10-03", "pickup_window": "10-13", "phone": "+7...",
 "respondent_name": "...", "respondent_address": "...", "note": "подъезд 2, код 15", "consent": true}
```
Ответ `{"order": Order}`. Ошибки (`detail.code`): `consent_required`, `slot_unavailable`, `courier_unavailable`,
`contact_required` (как у оплаты документа). Счёт: назначение `courier`, 3 990 ₸.

### Оплата — тот же экран Kaspi, что у документа
- `order.payment` — **та же форма, что `case.payment`** (`Payment` в `apps/web/lib/api.ts`: amount, currency, status,
  code, invoice_id, ways, …). Интерфейс показывает те же способы (`PaymentWays`) и, после слияния PR #145, ту же
  схему «Оплатить» в одно нажатие.
- Способ оплаты: уже существующий `POST /v1/invoices/{invoice_id}/way`.
- «Оплатил(а)»: `POST /v1/cases/{case_id}/courier/claim` → `{"order": Order}` (как `lawyer-payment/claim`).
- Оплату подтверждает тот же механизм (пуши Kaspi #149 / /ops «Оплаты»). После оплаты `order.status` → `ordered`.

### `POST /v1/cases/{case_id}/courier/answer` — «Загрузить ответ» (multipart, поле `files`, 1–5 файлов)
Ответ `{"order": Order}` со статусом `answered` и файлом в `answer_files`. Файл также кладётся в доказательства дела.

### Order
```json
{
  "id": 7, "status": "awaiting_payment",
  // awaiting_payment → ordered → picked_up → in_transit → delivered | refused → answered; cancelled
  "paid": false,
  "pickup_address": "...", "pickup_date": "2026-10-03", "pickup_window": "10-13", "pickup_window_label": "10:00–13:00",
  "respondent_name": "...", "respondent_address": "...",
  "carrier": "Алем ТАТ", "track_number": "AT123456", "track_url": "https://...",   // (необяз.) заполняет /ops
  "events": [{"status": "ordered", "at": "2026-10-01T19:00:00Z", "note": null}],     // по одному на смену статуса
  "delivered_at": null,
  "answer_due_at": "2026-10-14",   // дата вручения + срок ответа сценария (ЗПП — 10 дней); null до вручения
  "proof_files": [{"name": "второй экземпляр.jpg", "url": "/v1/files/..."}],         // отметка о получении / акт отказа
  "answer_files": [],
  "payment": { /* Payment, как case.payment */ }
}
```

## /ops (ключ или сессия администратора, `require_admin`)

### `GET /v1/admin/deliveries?status=<статус>|active|all`
`active` (по умолчанию) — всё, кроме `answered` и `cancelled`. Ответ:
```json
{"items": [{"id": 7, "case_id": "…", "case_title": "Возврат за услугу", "client_name": "Ахметов Е.", "client_phone": "+7…",
            "status": "ordered", "paid": true, "pickup_address": "…", "pickup_date": "2026-10-03", "pickup_window_label": "10:00–13:00",
            "respondent_name": "…", "respondent_address": "…", "carrier": null, "track_number": null, "track_url": null,
            "created_at": "…", "updated_at": "…", "answer_due_at": null, "test": false}],
 "counts": {"awaiting_payment": 1, "ordered": 2, "picked_up": 0, "in_transit": 1, "delivered": 0, "refused": 0, "answered": 0, "cancelled": 0}}
```

### `PATCH /v1/admin/deliveries/{id}`
Тело — любое из: `{"status": "picked_up", "carrier": "Алем ТАТ", "track_number": "AT123", "track_url": "https://…", "note": "…"}`.
Смена статуса пишет событие в `events`, клиенту — уведомление (push/e-mail, как у других статусов дела).
`delivered` ставит `delivered_at` и считает `answer_due_at`. Ответ — элемент списка.

### `POST /v1/admin/deliveries/{id}/proof` (multipart `files`) — фото второго экземпляра с отметкой или акт отказа.

## Тексты (готовы в интерфейсе, ru/kk)
Карточка, форма, инструкция «распечатайте 2 экземпляра и подпишите оба» (по § 5 справки юриста), согласие на передачу
данных курьерской службе — отдельная галочка (§ 4; название и БИН службы — после договора, пока «курьерская служба —
партнёр сервиса»). kk-тексты — черновик, вычитка носителем.
