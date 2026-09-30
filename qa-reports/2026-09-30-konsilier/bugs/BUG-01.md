**[🔴] Оплата — клиент сайта и приложения не может оплатить ни один документ**
Окружение: prod, api.konsilier.com, код @ 5a73aa6, 30.09.2026 ~19:50 UTC; сайт и PWA (тот же API)
Аккаунт/данные: новый анонимный клиент (`POST /v1/users`), дело kz.consumer.refund, документ 1 990 ₸
Шаги:
1. Создать клиента и дело, пройти анкету до «Проверьте данные» (`proposal.type = prepare_action`).
2. `POST /v1/cases/{id}/payment {"purpose":"document"}`.
3. Сервер отвечает `422 {"code":"contact_required","methods":["email"]}` — интерфейс просит подтвердить e‑mail.
4. `POST /v1/auth/email/start {"target":"info@konsilier.com"}`.
Фактический результат: `502 {"code":"send_failed"}` за 0,6 с. Код не приходит, счёт не создаётся, оплатить нельзя.
Ожидаемый результат: код приходит на почту → после подтверждения создаётся счёт → окно оплаты Kaspi.
Воспроизводимость: всегда — 13 из 13 дел (все сценарии), e‑mail 1 из 1.
Доказательства: evidence/logs/intake-13-cases.json (поле `pay`), evidence/logs/chat-15-clients.json (`payment_try`).
Гипотеза о причине: на сервере не задан RESEND_API_KEY / SMTP (см. team/sessions.md, пересечение 5; SPF/DKIM Resend в DNS есть).
`contact_to_confirm` (apps/api/konsilier/api/routes.py:593) при выключенном SMS требует e‑mail; вход по ЭЦП не засчитывается.
Смоук-пользователи (`is_test`) от этого требования освобождены, поэтому деплой-смоук блокер не видит.
Влияние: 0 оплат, 0 документов, 0 выручки с сайта и PWA. Оплатить можно только через Telegram-бот (ему контакт не нужен).
Что сделать: (а) задать ключ Resend на сервере; (б) до этого — решение владельца: PAYMENT_REQUIRES_CONTACT=false или засчитывать ЭЦП;
(в) добавить в deploy/smoke.py проверку отправки кода.
Автотест: scripts/runintake.py (шаг `pay`)
Метки: bug, blocker, web, pwa, payment, email
