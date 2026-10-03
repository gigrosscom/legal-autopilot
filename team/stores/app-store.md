# App Store: пакет App Store Connect для Konsiliér AI

Маркетолог и финансист, 30.09.2026. **Ничего не отправлено.** Аккаунт Apple Developer, сборка и отправка на
проверку — только после записи владельца в `decisions.md`.

Основа: `docs/app-stores.md` (путь для iOS — обёртка Capacitor с нативными функциями, 2–4 недели), соглашение
`apps/web/lib/legal/terms.ts`, модели данных `apps/api/konsilier/core/models.py` (ветка
`claude/zealous-volta-a3ipv6`). Правила Apple проверены 30.09.2026 на
[developer.apple.com/app-store/review/guidelines](https://developer.apple.com/app-store/review/guidelines/).

Разработчик: ТОО «Konsilier AI» (Konsilier AI LLP), БИН 260940036818, 050000, г. Алматы, Наурызбайский район,
мкр. Курамыс, ул. Акселеу Сейдимбек, д. 222. E-mail: info@konsilier.com.

---

## 0. Блокеры до отправки (важно)

| # | Блокер | Правило Apple (цитата) | Что сделать |
|---|---|---|---|
| 1 | **Минимальная функциональность.** Обёртку сайта отклоняют | 4.2: «Your app should include features, content, and UI that elevate it beyond a repackaged website.» | Реализовать нативные функции из `docs/app-stores.md` (раздел 3 ниже). Отправлять только когда они работают |
| 2 | **Оплата документов.** Документ, который готовит сервис, — это цифровой контент, который открывается в приложении. Для него Apple требует In-App Purchase | 3.1.1: «If you want to unlock features or functionality within your app… you must use in-app purchase.» 3.1.1(a): во всех витринах, кроме США, нельзя кнопок и ссылок на другие способы оплаты | Решение владельца: **(А)** документы в iOS — через IAP (расходуемые покупки); **(Б)** в iOS-версии нет покупок вообще. Но вариант Б **не позволяет** открывать в iOS документы, купленные на сайте, если их нельзя купить через IAP: 3.1.3(b) разрешает доступ к купленному на других платформах, «provided those items are also available as in-app purchases within the app». Оплату на Kaspi в iOS-версии не показывать ни в каком варианте |
| 3 | **Правило 3.1.3(e) к документам не относится.** Оно — про товары и услуги, которые потребляются вне приложения: «If your app enables people to purchase physical goods or services that will be consumed outside of the app, you must use purchase methods other than in-app purchase». Документ сервис создаёт и выдаёт в приложении, поэтому ссылаться на 3.1.3(e) для документов рискованно (оценка, проверить) | 3.1.3(e) | 3.1.3(e) применимо к **услугам юриста**: их клиент получает вне приложения и оплачивает юристу напрямую по договору (соглашение п. 4.1). Через приложение эти деньги не идут — так и написать в заметках для проверки |
| 4 | **Подписка юристов.** Доступ к платформе за деньги — цифровая функциональность | 3.1.1 | В iOS-версии не продавать подписку юристов и не показывать цены на неё |
| 5 | **Удаление аккаунта в приложении.** Сейчас его нет (только письмо или форма /support) | 5.1.1(v): «If your app supports account creation, you must also offer account deletion within the app.» | Задача продукту: кнопка «Удалить аккаунт» в /account |
| 6 | **Политика конфиденциальности** — ссылка в метаданных и в приложении; должна описывать данные, третьих лиц и удаление | 5.1.1(i) | Сейчас это раздел 9 соглашения на /terms. Лучше отдельная /privacy; дописать, что обработчики (ИИ-провайдер, почта, SMS, хостинг) защищают данные не хуже нас |
| 7 | **Регулируемая сфера — подавать от юрлица** | 5.1.1(ix): регулируемые сферы «should be submitted by a legal entity that provides the services, and not by an individual developer». Право в списке примеров не названо | Подавать от ТОО, не от физлица. Это и так нужно для D-U-N-S |

---

## 1. Карточка

| Поле | Значение |
|---|---|
| Name (до 30) | **Konsiliér AI** (12) |
| Subtitle ru (до 30) | `ИИ-помощник: права и документы` (30) |
| Subtitle en (до 30) | `AI help with legal questions` (28) |
| Bundle ID | `com.konsilier.app` (как в `docs/app-stores.md`) |
| SKU | `konsilier-ios-1` |
| Primary category | Productivity (Производительность). Secondary: Reference (Справочники) — предложение, решает владелец |
| Основная локализация | Russian. Дополнительно: English (U.K. или U.S.). Казахского в списке локализаций App Store Connect, по нашим данным, нет — **проверить**; казахские слова можно добавить в ключевые слова русской локализации |
| Витрина | Казахстан (при выборе других стран — проверить, что сервис там полезен; сейчас он только для РК) |
| Цена приложения | Бесплатно |
| Support URL | https://konsilier.com/support |
| Marketing URL | https://konsilier.com |
| Privacy Policy URL | https://konsilier.com/terms (раздел 9) — до появления /privacy |
| Copyright | 2026 Konsilier AI LLP |

### 1.1. Promotional text (до 170)

- ru (138): `Опишите ситуацию своими словами — Konsiliér AI разъяснит ваши права со ссылкой на закон, подготовит документ и подскажет, куда его подать.`
- en (147): `Describe your situation in your own words. Konsiliér AI explains your rights with links to the law, drafts the document and shows where to file it.`

### 1.2. Keywords (до 100 символов, через запятую без пробелов)

- ru (97): `юрист,претензия,жалоба,заявление,возврат,зарплата,штраф,алименты,кредит,долг,заң,заңгер,шағым,иск`
- en (99): `lawyer,claim,complaint,refund,wages,fine,alimony,loan,fraud,rights,Kazakhstan,legal,letter,deadline`

Казахские слова (заң, заңгер, шағым) требуют вычитки носителем.

### 1.3. Description (до 4 000)

Строки с пометкой [iOS] включать, только если функция реализована в сборке (блокер 1). Про покупки — по решению
по блокеру 2.

**ru** (1 876 символов)

```
Konsiliér AI — ИИ-помощник по юридическим вопросам.

Опишите ситуацию своими словами, на русском или казахском: вернуть деньги за товар или услугу, получить зарплату при увольнении, оспорить кредит, который оформили мошенники, обжаловать штраф, вернуть залог за аренду. Konsiliér AI объяснит, какие у вас права и что делать дальше.

ЧТО УМЕЕТ ПРИЛОЖЕНИЕ
• Чат с ИИ-помощником — бесплатно, с дневным лимитом сообщений. Нормы закона — со ссылкой на официальный текст в ИПС «Әділет».
• Документ по вашей ситуации: претензия, жалоба, заявление. Сервис задаст недостающие вопросы и соберёт документ в DOCX и PDF.
• Куда и как подать: адресат, способ подачи и пошаговая инструкция.
• Сроки: посчитаем срок ответа и напомним о нём.
• Мои дела: история, документы и файлы по каждому делу в одном месте.
• Голосовой ввод, если удобнее говорить, чем писать.
• Каталог юристов для сложных ситуаций. Договор о юридической помощи вы заключаете с юристом напрямую.

НА IPHONE
• [iOS] Сканер документов: снимите договор или чек камерой — страница обрежется и выровняется и сразу попадёт в дело.
• [iOS] Уведомления о сроках и ответах.
• [iOS] Вход по Face ID или Touch ID после первого входа.
• [iOS] Отправка файлов в приложение через «Поделиться» и открытие PDF и DOCX из «Файлов».
• [iOS] Скачанные документы доступны без интернета.

КОНФИДЕНЦИАЛЬНОСТЬ
Имена, ИИН, телефоны и адреса заменяются метками до передачи текста ИИ. Серверы и файлы сервиса хранятся в Казахстане.

ВАЖНО
Konsiliér AI — IT-сервис. Ответы ИИ — справочная информация, документы — проекты: проверьте сведения перед подачей. Сервис не представляет ваши интересы и не гарантирует исход дела. В сложных ситуациях обратитесь к адвокату или юридическому консультанту. Если угрожает опасность — звоните 112.

Сейчас сервис работает для Казахстана.

Оператор: ТОО «Konsilier AI», г. Алматы. Поддержка: info@konsilier.com.
```

**en** (2 021 символ)

```
Konsiliér AI is an AI assistant for legal questions.

Describe your situation in your own words, in Russian or Kazakh: getting a refund for a product or service, getting your wages after dismissal, disputing a loan taken out by fraudsters, appealing a fine, getting a rental deposit back. Konsiliér AI explains your rights and what to do next.

WHAT THE APP DOES
• AI assistant chat — free, with a daily message limit. Statutes are linked to the official text in the Adilet legal database.
• A document for your situation: a pre-trial claim, complaint or application. The service asks for the missing facts and builds the document in DOCX and PDF.
• Where and how to file: the addressee, the filing channel and step-by-step instructions.
• Deadlines: we count the response deadline and remind you.
• My cases: history, documents and files for each case in one place.
• Voice input when speaking is easier than typing.
• A lawyer directory for complex situations. You sign the legal services contract with the lawyer directly.

ON IPHONE
• [iOS] Document scanner: photograph a contract or receipt; the page is cropped, straightened and added to your case.
• [iOS] Notifications about deadlines and responses.
• [iOS] Face ID or Touch ID sign-in after the first sign-in.
• [iOS] Send files to the app with Share and open PDF and DOCX files from Files.
• [iOS] Downloaded documents are available offline.

PRIVACY
Names, national ID numbers, phone numbers and addresses are replaced with placeholders before any text is sent to the AI. The service's servers and files are stored in Kazakhstan.

IMPORTANT
Konsiliér AI is an IT service. AI answers are reference information and documents are drafts: check the details before filing. The service does not represent you and does not guarantee the outcome of your case. In complex situations, contact an advocate or a legal consultant. If you are in danger, call 112.

The service currently covers Kazakhstan.

Operator: Konsilier AI LLP, Almaty. Support: info@konsilier.com.
```

---

## 2. Возрастной рейтинг (анкета App Store Connect)

Анкету Apple обновила в 2025 году (рейтинги 4+, 9+, 13+, 16+, 18+; новые блоки: встроенные ограничения,
возможности приложения, медицинские темы, насилие) —
[developer.apple.com/news/?id=ks775ehf](https://developer.apple.com/news/?id=ks775ehf). Точные формулировки
вопросов проверить в форме.

| Вопрос | Ответ | Почему |
|---|---|---|
| Насилие (мультяшное, реалистичное, продолжительное), кровь | None | Нет такого контента |
| Сексуальный контент, нагота | None | — |
| Ненормативная лексика, грубый юмор | None | — |
| Алкоголь, табак, наркотики | None | — |
| Хоррор, страх | None | — |
| Азартные игры, симулированные азартные игры, конкурсы | None / No | — |
| Взрослые или наводящие на размышления темы | Infrequent/Mild — **проверить**: ИИ может обсуждать ситуации вроде домашнего насилия (сервис направляет на 112) и споры о детях | Честнее отметить «редко» |
| Medical or Treatment Information / медицинские темы | None — **проверить**: сервис не даёт медицинских советов; есть споры о платной медицине как потребительские | — |
| Unrestricted Web Access | No | Приложение открывает только konsilier.com и официальные страницы по ссылкам в Safari |
| User-generated content / Messaging and Chat | Чат — с ИИ, не между людьми. Между пользователями: только заявка юристу и подписание согласия и договора | Отметить честно по формулировке вопроса; при сомнении — «Yes» для обмена с юристом |
| Advertising | No | Рекламы нет |
| Parental controls / age assurance | No | — |

Ожидаемый итоговый рейтинг — низкий (4+ или 9+). Приложение всё равно рассчитано на взрослых (18+): это можно
указать в описании, но не нужно завышать рейтинг ответами.

---

## 3. App Privacy («этикетка питания»)

Составлено по коду (`models.py`, `api/transcribe.py`, `core/llm/redacting.py`, `config.py`) и разделу 9
соглашения. Отслеживания (tracking) нет: рекламы и SDK аналитики нет (поиск по коду 30.09.2026).

**Do you or your third-party partners collect data from this app?** Yes.
**Data used to track you:** None.

Все типы ниже: **Linked to the user** — да (дела привязаны к аккаунту); **Used for tracking** — нет.

| Тип данных Apple | Собираем | Цели (Purposes) | Что именно |
|---|---|---|---|
| Contact Info → Name | Да | App Functionality | Имя в профиле, стороны дела, заявка юристу |
| Contact Info → Email Address | Да | App Functionality; Developer's Communications | Вход, напоминания, ответы поддержки |
| Contact Info → Phone Number | Да | App Functionality | Вход, SMS-код перед оплатой, заявка юристу |
| Contact Info → Physical Address | Да | App Functionality | Адреса сторон в документе |
| Contact Info → Other User Contact Info | Нет | — | — |
| Health & Fitness → Health | Да, только если пользователь сам сообщил (отдельное согласие) | App Functionality | Сведения о здоровье в деле |
| Financial Info → Payment Info | Нет (при IAP оплату обрабатывает Apple) | — | Номера карт не собираем |
| Financial Info → Other Financial Info | Да | App Functionality | Суммы требований и история оплат документов |
| Sensitive Info | Да — **проверить трактовку**: ИИН мы храним только как хэш для входа; данные о здоровье — выше | App Functionality | — |
| User Content → Photos or Videos | Да | App Functionality | Фото документов в деле |
| User Content → Audio Data | Да, не хранится | App Functionality | Голос → текст, аудио не сохраняется и не пишется в журнал |
| User Content → Customer Support | Да | App Functionality | Обращения в поддержку |
| User Content → Other User Content | Да | App Functionality | Описание ситуации, сообщения чата, загруженные файлы, документы |
| Identifiers → User ID | Да | App Functionality | Внутренний id аккаунта |
| Identifiers → Device ID | Да, если будут нативные push (токен APNs) | App Functionality | Push-токен устройства |
| Usage Data → Product Interaction | Да, минимально | Analytics | Источник перехода и реферальный код |
| Diagnostics | Нет (SDK нет) | — | Проверить перед отправкой |
| Location, Contacts, Browsing History, Search History, Purchases (Apple-тип «Purchase History») | Purchase History — да (оплаченные документы); остальное — нет | App Functionality | — |

---

## 4. Review notes (App Review Information, EN — вставлять как есть после реализации)

```
Konsiliér AI is an AI assistant for everyday legal questions in Kazakhstan, operated by Konsilier AI LLP (BIN 260940036818, Almaty). It is an IT service, not a law firm: the app explains a user's situation, drafts documents (pre-trial claims, complaints, applications) from structured scenarios and shows where to file them. Every document is marked as prepared by an IT service and the user checks it before filing.

Native features (Guideline 4.2) — these are not available on our website:
1. Document scanner (VisionKit): capture a contract or receipt with the camera; the page is cropped, straightened and attached to the case.
2. Push notifications via APNs for filing deadlines and responses.
3. Face ID / Touch ID sign-in after the first sign-in (token stored in the Keychain).
4. Share extension: send PDF, DOCX or images from other apps to a case; open documents from the Files app.
5. Offline access to downloaded documents.

Payments:
- Documents prepared in the app are sold only through In-App Purchase (Guideline 3.1.1). The app has no buttons, links or other calls to action for any other payment method.
- The app does not sell legal services. Lawyers listed in the directory contract with clients directly; their services are provided outside the app and no payment for them passes through the app (Guideline 3.1.3(e)).
- Lawyer subscriptions are not offered in the iOS app.

Account deletion: Account → Delete account (Guideline 5.1.1(v)).
Reporting: every AI answer has a "Report a problem" button.

Demo account (Kazakhstan, test data only):
E-mail: [owner: test account e-mail]
Code: [owner: fixed sign-in code for the test account, or password]
Suggested path: Chat → ask "The store refuses to refund a faulty phone" → Start a case → answer the questions → view the document preview.

Contact: [owner: name, phone], info@konsilier.com
```

Если выбран вариант Б (без покупок в iOS), абзац «Payments» заменить на: «The iOS app does not offer any purchases.
Documents are not unlocked in the app.» — и убрать из приложения доступ к документам, купленным на сайте (см.
блокер 2).

---

## 5. Сборка (кратко, по `docs/app-stores.md`)

1. `npm i @capacitor/core @capacitor/ios` → `npx cap init "Konsiliér AI" com.konsilier.app` → приложение грузит
   https://konsilier.com плюс нативные плагины: push (APNs, серверная отправка — отдельная задача), сканер
   документов, биометрия, Share Extension, офлайн-документы.
2. IAP для документов (вариант А) — StoreKit и серверная проверка покупок: отдельная задача продукту.
3. `npx cap add ios` → сборка в Xcode (Mac) или в облаке (Codemagic / Ionic Appflow) → TestFlight → отправка.
4. Скриншоты: iPhone 6,9″ (и 6,5″, если потребует форма), iPad — если приложение для iPad. Список экранов — как в
   `team/stores/google-play.md`, раздел 4, плюс экран сканера.

---

## 6. Что должен сделать владелец

1. Решение по оплате в iOS (блокер 2: вариант А — IAP или вариант Б — без покупок) и по подписке юристов (блокер 4).
2. D-U-N-S для ТОО «Konsilier AI»: бесплатно; Apple пишет — до 5 рабочих дней у D&B и до 2 рабочих дней до
   передачи в Apple. Название должно совпадать с юридическим; ИП не подходит.
3. Apple ID владельца с двухфакторной защитой; вступление в Apple Developer Program **как организация**: $99 в год;
   сайт компании должен быть рабочим и на домене компании; право подписывать договоры от ТОО.
4. Mac с Xcode или облачная сборка.
5. Тестовый аккаунт для проверяющих Apple (e-mail и постоянный код или пароль), с вымышленными данными.
6. Одобрить задачи продукту: нативные функции (блокер 1), удаление аккаунта (5), политика конфиденциальности (6),
   кнопка «Сообщить о проблеме» у ответа ИИ.
7. Если нужны платные приложения или IAP: соглашение Paid Apps, банковские и налоговые данные в App Store Connect.
8. Запись в `decisions.md`: «публиковать в App Store».

## Источники (открыты 30.09.2026)

- App Review Guidelines: https://developer.apple.com/app-store/review/guidelines/ — 3.1.1, 3.1.1(a), 3.1.3(b), 3.1.3(d), 3.1.3(e), 3.1.3(f), 4.2, 5.1.1(i), 5.1.1(v), 5.1.1(ix), 2.3.6.
- D-U-N-S для Apple: https://developer.apple.com/help/account/membership/D-U-N-S/
- Вступление: https://developer.apple.com/programs/enroll/ ($99 в год, требования к юрлицу и сайту — по выдаче поиска и сторонним гидам, проверить на странице).
- Новая анкета возрастного рейтинга: https://developer.apple.com/news/?id=ks775ehf
