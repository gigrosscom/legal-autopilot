# WhatsApp-бот Konsiliér AI — что нужно и как подключить

**Решение владельца 01.10.2026:** открыть бизнес-аккаунт WhatsApp и сделать бота на том же движке, что Telegram-бот.
Бот отвечает только тем, кто написал сам.

Подготовил: Интегратор, 01.10.2026. Код бота — ветка `claude/team-whatsapp` (срок 03.10).

---

## 1. Коротко

- Боту нужна **WhatsApp Business Platform (Cloud API от Meta)**. Обычное приложение WhatsApp Business не подходит.
- Номер для бота — **отдельный**. Он не должен быть в приложении WhatsApp (ни обычном, ни Business).
- Пишем только тем, кто написал первым, и только в течение **24 часов** после его последнего сообщения.
  Тогда шаблоны и согласие на рассылку не нужны.
- С **01.10.2026** ответы в чате (service) **платные сверх 1 000 в месяц на номер**: Казахстан — **$0,018** за сообщение.
- **Главный риск — правила Meta для ИИ-сервисов** (раздел 6). Его надо учесть до запуска.

---

## 2. WhatsApp Business App или Business Platform

| | WhatsApp Business App | WhatsApp Business Platform (Cloud API) |
|---|---|---|
| Что это | Приложение на телефоне | API на серверах Meta |
| Кто отвечает | Человек вручную (есть простые автоответы) | Наш сервер (бот) |
| Бот с ИИ, файлы на сервер | Нет | Да |
| Цена | Бесплатно | Оплата за сообщения (раздел 5) |
| Номер | Один телефон | Номер нельзя одновременно держать в приложении WhatsApp |

**Вывод:** для бота — только Cloud API. Приложение WhatsApp Business на этот номер не ставить.

Источник: Meta, «Business phone numbers» — «Registered numbers … cannot be used with WhatsApp Messenger»
(developers.facebook.com/documentation/business-messaging/whatsapp/business-phone-numbers/phone-numbers, открыто 01.10.2026).

---

## 3. Пошагово для владельца

### Шаг 1. Бизнес-портфолио в Meta (business.facebook.com)
1. Войти на **business.facebook.com** со своего Facebook-аккаунта.
2. Создать бизнес-портфолио: название **Konsilier AI LLP**, e-mail — рабочий (info@ или dev@ домена konsilier.com).
3. Добавить второго администратора (на случай потери доступа).

### Шаг 2. Подтверждение компании (Business verification)
1. Business Settings → **Security Center** → **Start verification**.
2. Данные ТОО:
   - юридическое название: **ТОО «Konsilier AI»**; на латинице — **Konsilier AI LLP**;
   - БИН: **260940036818**;
   - адрес и телефон — как в регистрационных документах;
   - сайт: **konsilier.com** (на сайте должно быть видно название ТОО — проверить подвал).
3. Документы: справка о государственной регистрации юрлица (egov.kz) и/или свидетельство с БИН.
   Название и адрес в документах должны совпадать с введёнными.
4. Подтверждение — кодом на e-mail домена konsilier.com или звонком/SMS на номер компании.
5. Срок — на стороне Meta; закладываем до двух недель. **Без подтверждения бот тоже работает**, но шаблонами вне окна можно
   написать не больше чем 250 разным людям за 30 дней. Для ответов тем, кто написал сам, лимит не действует (раздел 4).

### Шаг 3. Номер телефона
- Отдельная **мобильная** SIM (Meta рекомендует мобильный номер; стационарные, виртуальные и платные номера — «Not Recommended»).
- Номер с кодом страны (+7 7…), принимает SMS или звонок. Короткие номера не подходят.
- Номер **не должен быть** в приложении WhatsApp. Если был — удалить там аккаунт (Настройки → Аккаунт → Удалить аккаунт).
- SIM держать у владельца: по ней восстанавливается доступ.
- Включить двухшаговую проверку (PIN из 6 цифр) — Meta требует её при регистрации номера. PIN — в менеджер паролей, не в файлы.

### Шаг 4. Отображаемое имя (display name)
- Предлагаем: **Konsilier AI** (как бренд и название ТОО).
- Правила Meta: имя должно быть связано с компанией и подтверждаться сайтом/документами; без эмодзи и лишних символов;
  без общих слов в одиночку («Legal», «Юрист»); без чужих брендов.
  Полный список — статья Meta «Display name guidelines» (facebook.com/business/help/757569725593362) — **у нас без входа
  не открылась, владельцу сверить при вводе имени**.
- Имя проверяется после подтверждения компании. Менять — не больше 10 раз за 30 дней; после одобрения нового имени номер
  надо перерегистрировать в течение 14 дней (это сделаем мы).

### Шаг 5. Приложение в developers.facebook.com
1. **developers.facebook.com** → My Apps → **Create app**.
2. Сценарий: **«Connect with customers through WhatsApp»** (тип Business). Привязать к портфолио Konsilier AI LLP.
3. Meta создаст WhatsApp Business Account (WABA) и тестовый номер.
4. WhatsApp → **API Setup** → **Add phone number** → ввести номер из шага 3, имя из шага 4, подтвердить кодом из SMS.
5. Скопировать **Phone number ID** (не сам номер!) → это `WHATSAPP_PHONE_ID`.
6. App settings → Basic → **App secret** → **Show** → это `WHATSAPP_APP_SECRET`.
7. Добавить способ оплаты: WhatsApp Manager → Account tools → Payment methods (карта ТОО). Без него после 1 000 бесплатных
   ответов в месяц сообщения не уйдут.

### Шаг 6. Постоянный токен (System User)
Временный токен со страницы API Setup живёт около суток — для сервера не годится.
1. business.facebook.com → **Business Settings** → **Users → System users** → **Add**.
2. Имя: `konsilier-bot`, роль **Admin**.
3. **Assign assets**: приложение из шага 5 — **Manage app (Full control)**; WhatsApp-аккаунт — **Full control**.
4. **Generate token** → выбрать приложение → срок действия **Never** → разрешения:
   `business_management`, `whatsapp_business_messaging`, `whatsapp_business_management`.
5. Скопировать токен **один раз** → это `WHATSAPP_TOKEN`. В файлы, чаты и Telegram не вставлять — только в настройки сервера.

### Шаг 7. Webhook (адрес, куда Meta шлёт сообщения)
1. Придумать **verify token** — любая длинная случайная строка (например, 32 символа) → это `WHATSAPP_VERIFY_TOKEN`.
2. Задать на сервере четыре переменные (раздел 7) и перезапустить.
3. App Dashboard → WhatsApp → **Configuration** (или Use cases → Customize → Configuration):
   - **Callback URL**: `https://api.konsilier.com/whatsapp/webhook` (работает после выкладки ветки `claude/team-whatsapp`);
   - **Verify token**: та же строка, что `WHATSAPP_VERIFY_TOKEN`;
   - **Verify and save**. Meta отправит проверочный GET — сервер ответит сам.
4. В списке полей подписаться на **messages** (только это поле).
5. Проверка: написать на номер бота со своего WhatsApp → бот отвечает.

### Шаг 8. Шаблоны сообщений (message templates)
- **Сейчас не нужны.** Бот отвечает только в 24-часовом окне после сообщения клиента.
- Понадобятся, если захотим писать клиенту позже 24 часов (например, «документ готов» на следующий день,
  напоминание о сроке ответа органа). Тогда — шаблон категории **Utility**, на одобрение (до 24 часов),
  и согласие клиента получать такие сообщения в WhatsApp.
- Маркетинговые рассылки не планируем (решение: бот отвечает только тем, кто написал сам).

---

## 4. Ограничения

- **24-часовое окно (customer service window).** После каждого сообщения клиента 24 часа можно отвечать чем угодно.
  После — только одобренным шаблоном. Бот это проверяет и вне окна молчит.
- **Первыми не пишем.** Начать разговор бизнес может только шаблоном и при согласии (opt-in) клиента.
- **Лимиты (messaging limits)** — сколько **разных** людей можно достать шаблонами **вне окна** за 30 дней (скользящее окно):
  новый портфолио — **250**; после подтверждения компании — **2 000**; дальше автоматически **10 000 → 100 000 → без лимита**,
  если за 7 дней использована половина лимита и качество высокое. **На ответы в открытом окне лимит не влияет.**
- **Качество (quality rating).** Жалобы и блокировки клиентов снижают рейтинг и могут ограничить номер.
- Одно сообщение — до **4 096 символов**. Медиа от клиента: аудио до 16 МБ, документы до 100 МБ; ссылка на файл живёт 5 минут
  (сервер скачивает сразу).

Источники: «Messaging limits», «Templates overview», «Text messages», «Media»
(developers.facebook.com/documentation/business-messaging/whatsapp/…, открыто 01.10.2026).

---

## 5. Цены Meta для Казахстана (оплата за сообщение)

С 01.07.2025 Meta берёт плату **за доставленное сообщение**, а не за «разговор». Входящие от клиента — бесплатно.
С **01.10.2026** Казахстан — отдельный рынок (раньше входил в «Rest of Central & Eastern Europe»).

**Тарифы, USD за сообщение, действуют с 01.10.2026:**

| Категория | Казахстан | Для сравнения: Rest of CEE |
|---|---|---|
| Marketing (реклама, шаблон) | **0,0604** | 0,0860 |
| Utility (служебный шаблон: «документ готов») | **0,0180** (в открытом окне — бесплатно) | 0,0212 |
| Authentication (коды входа) | **0,0180** | 0,0212 |
| Authentication-International | **0,1600** | — |
| **Service (ответы в окне 24 ч)** | **0,0180** после **1 000 бесплатных в месяц на номер** | 0,0212 |

Что это значит для нас:
- Бот отвечает только в окне → платим только за **service**: первые **1 000** ответов в месяц на номер — бесплатно,
  дальше **$0,018** за каждое доставленное сообщение. Неиспользованные бесплатные не переносятся.
- Длинный ответ, разбитый на 3 сообщения, — это 3 сообщения. Бот режет ответ только когда он длиннее 4 096 символов.
- Оценка: 300 клиентов × 10 ответов = 3 000 сообщений → 2 000 платных × $0,018 = **$36 в месяц**.
- Скидки за объём (volume tiers) для utility/authentication в Казахстане — от 80 000 / 100 000 сообщений в месяц; нам не актуально.
- Meta меняет цены только 1 января, 1 апреля, 1 июля и 1 октября; предупреждает за месяц.

Источники (открыты 01.10.2026):
- Meta, «Pricing on the WhatsApp Business Platform» — developers.facebook.com/docs/whatsapp/pricing
  (разделы «Service rates, effective October 1, 2026», «Rate card updates, effective October 1, 2026»: «Increases in Kazakhstan*…»).
- Тарифная сетка USD «Cost per message in USD … effective October 1, 2026» (List rates и Volume tiers) — файл по ссылке
  «USD rates» в разделе «Rate cards effective October 1, 2026» той же страницы. Строка: `Kazakhstan, USD, 0.0604, 0.018, 0.018, 0.16, 0.018`.
- Прежняя сетка «effective July 1, 2026»: Rest of Central & Eastern Europe — 0.0860 / 0.0212 / 0.0212 (Service — n/a, т.е. бесплатно до 30.09.2026).

---

## 6. Риск: правила Meta для ИИ-сервисов

- В «Meta Terms for WhatsApp Business Platform» (изменены 23.09.2026), п. 4.7: поставщикам ИИ — LLM, генеративным платформам,
  **ИИ-ассистентам общего назначения** — пользоваться платформой **запрещено**, если ИИ — **основная** функция,
  а не вспомогательная. Решает Meta «по своему усмотрению».
- Исключения — только страны, где Meta обязана пускать таких поставщиков (ЕС и др.); **Казахстана в списке нет**
  (страница «Pricing policy for AI Providers», открыта 01.10.2026).
- Как снижаем риск:
  - бот — канал **сервиса подготовки правовых документов** ТОО: дело, доказательства, оплата, готовый документ;
  - бот не отвечает на вопросы не по теме (уже так на сайте — коротко возвращает к правовым вопросам);
  - в описании профиля и при подтверждении компании — «Сервис подготовки правовых документов», а не «ИИ-ассистент».
- Если Meta отклонит номер или заблокирует — Telegram и сайт продолжают работать; бот WhatsApp выключается одной настройкой.
- **Нужно решение владельца:** запускать WhatsApp при этом риске (рекомендуем — да, с формулировками выше).

---

## 7. Переменные на сервере (задаёт владелец)

| Переменная | Откуда | Пример формата |
|---|---|---|
| `WHATSAPP_TOKEN` | Шаг 6, токен System User | длинная строка `EAA…` |
| `WHATSAPP_PHONE_ID` | Шаг 5, Phone number ID | цифры, ~15 знаков |
| `WHATSAPP_APP_SECRET` | Шаг 5, App secret | 32 hex-символа |
| `WHATSAPP_VERIFY_TOKEN` | Шаг 7, придумать самому | любая длинная строка |

- Пока хоть одна не задана — бот **выключен**, адрес webhook отвечает 404.
- Значения — только в настройках сервера (`konsilier-env`). В git, файлы и чаты не записывать.

---

## 8. Что делает бот (код — ветка `claude/team-whatsapp`, `apps/bot/konsilier_bot/whatsapp/`)

- Тот же движок (API), что Telegram-бот и чат сайта.
- Первое сообщение человека → приветствие со ссылкой на соглашение; описание ситуации идёт дальше по кнопке «Продолжить».
- Дальше — ответы чата ИИ (как на сайте), оформление под WhatsApp (*жирный*, _курсив_, списки «•»).
- Под ответом — «Составить документ», когда чат его предлагает. Дальше — как в Telegram: до 4 вопросов,
  оплата переводом на Kaspi с кодом и кнопкой «Оплатить», готовый документ приходит файлом.
- Голосовые → расшифровка (Gemini, бесплатно); фото и PDF → доказательства в деле.
- Личная ссылка на дело на сайте (черновик, оплата, документы): одноразовая, живёт 1 час.
- Слова-команды: «новое дело», «статус», «документ», «сайт», «помощь».
- Уведомления сервера (оплата подтверждена, документ готов) уходят в WhatsApp только в открытом окне 24 ч; иначе — на сайт, e-mail, SMS.
- Проверяет подпись каждого запроса от Meta (`X-Hub-Signature-256`, ключ — `WHATSAPP_APP_SECRET`).
- Одно и то же сообщение дважды не обрабатывает (Meta повторяет доставку до 7 дней).
- Статусы «доставлено/прочитано» спокойно пропускает.
- Вне 24-часового окна ничего не отправляет.

---

## 9. Источники (все открыты 01.10.2026)

1. Pricing on the WhatsApp Business Platform — https://developers.facebook.com/docs/whatsapp/pricing/
2. Rate card USD, effective October 1, 2026 (List rates, Volume tiers) — ссылки «USD rates» / «USD volume tiers» на странице 1.
3. Rate card USD, effective July 1, 2026 — там же, для сравнения.
4. Pricing policy for AI Providers — https://developers.facebook.com/documentation/business-messaging/whatsapp/pricing/ai-providers/
5. Meta Terms for WhatsApp Business Platform (Last modified 23.09.2026), п. 4.7 — https://www.facebook.com/legal/Meta-Terms-for-WhatsApp-Business-Platform
6. Get started (Cloud API) — https://developers.facebook.com/docs/whatsapp/cloud-api/get-started
7. Access tokens (System User) — https://developers.facebook.com/documentation/business-messaging/whatsapp/access-tokens/
8. Create a webhook endpoint — https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/create-webhook-endpoint/
9. Business phone numbers — https://developers.facebook.com/documentation/business-messaging/whatsapp/business-phone-numbers/phone-numbers/
10. Register a business phone number — https://developers.facebook.com/documentation/business-messaging/whatsapp/business-phone-numbers/registration/
11. Display names — https://developers.facebook.com/documentation/business-messaging/whatsapp/display-names/
12. Messaging limits — https://developers.facebook.com/documentation/business-messaging/whatsapp/messaging-limits/
13. Templates overview — https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/overview/
14. Text messages (4 096 символов) — https://developers.facebook.com/documentation/business-messaging/whatsapp/messages/text-messages/
15. Media (ссылка живёт 5 минут, размеры) — https://developers.facebook.com/documentation/business-messaging/whatsapp/business-phone-numbers/media/

Не открылись без входа (сверить владельцу): Display name guidelines (facebook.com/business/help/757569725593362),
статья о подтверждении компании (facebook.com/business/help/1095661473946872).
