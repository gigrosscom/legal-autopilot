# Приложение в магазинах: Google Play, App Store, Microsoft Store

Сейчас Консильéр ставится прямо с сайта (страница **konsilier.com/app**): Android, iPhone/iPad (iOS 16.4+, через
«На экран «Домой»»), Windows и Mac. Вход, уведомления (web push) и загрузка файлов работают в установленном приложении.
Магазины — следующий шаг: они дают поиск в каталоге и доверие, но требуют аккаунтов разработчика на компанию.
Ниже — что нужно от основателя и что делаем мы. Ничего из этого ещё не отправлено.

## Что уже готово в коде

- Манифест `apps/web/app/manifest.webmanifest/route.ts`: название, иконки (в т.ч. maskable и монохромная), ярлыки (Новое дело, Мои дела,
  Чат), `share_target` (приём файлов из других приложений на Android).
- Service worker `apps/web/public/sw.js`: офлайн-страница, push-уведомления, приём файлов.
- Push с сервера: ключи VAPID (`python deploy/vapid_keys.py` → `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY` в `.env`).
- `https://konsilier.com/.well-known/assetlinks.json` — отдаётся сайтом; заполняется переменными
  `ANDROID_PACKAGE` (по умолчанию `com.konsilier.app`) и `ANDROID_CERT_SHA256`.

## 1. Google Play — Trusted Web Activity (быстро, 1–3 дня)

**Нужно от основателя:** аккаунт Google Play Console на организацию — **$25 один раз**
(play.google.com/console; для организации нужен D-U-N-S номер и проверка документов), политика конфиденциальности по
ссылке (есть: /terms), контакт поддержки.

**Шаги:**
1. Сборка обёртки из нашего манифеста (Bubblewrap от Google):
   ```
   npm i -g @bubblewrap/cli
   bubblewrap init --manifest https://konsilier.com/manifest.webmanifest
   # packageId: com.konsilier.app, имя: Konsiliér AI, ключ подписи — создать новый (хранить в сейфе!)
   bubblewrap build        # → app-release-bundle.aab
   ```
   Альтернатива без командной строки — pwabuilder.com → Android.
2. В Play Console: создать приложение, включить **Play App Signing**, загрузить `.aab` во внутреннее тестирование.
3. Скопировать **SHA-256 отпечаток ключа подписи приложения** (Play Console → «Целостность приложения»), а также
   отпечаток ключа загрузки, и прописать на сервере через запятую:
   `ANDROID_CERT_SHA256=AA:BB:...,CC:DD:...` → передеплой. Проверить: https://konsilier.com/.well-known/assetlinks.json
   (без этого Android показывает адресную строку браузера внутри приложения).
4. Заполнить карточку (скриншоты телефона, описание, возрастной рейтинг, анкета «Безопасность данных»), затем
   закрытое тестирование: новым личным аккаунтам Google требует 12 тестировщиков 14 дней; аккаунт организации — нет.
5. Push, вход и загрузка файлов работают как на сайте — это тот же сайт на весь экран.

## 2. App Store (iPhone/iPad) — обёртка Capacitor с нативными функциями (2–4 недели)

**Нужно от основателя:** Apple Developer Program на организацию — **$99 в год** (developer.apple.com; D-U-N-S номер),
Mac с Xcode для сборки (или облачная сборка, например Codemagic / Ionic Appflow), тестовый аккаунт для проверяющих Apple.

**Главный риск — правило App Store 4.2 (Minimum Functionality):** приложение, которое просто открывает сайт в окне,
отклоняют («repackaged website»). Нужно добавить то, чего нет в Safari:
- **нативные push через APNs** (плагин `@capacitor/push-notifications`; сервер: добавить отправку в APNs рядом с
  web push — отдельная задача);
- **сканер документов камерой** с обрезкой и выравниванием (VisionKit / плагин document-scanner) → сразу в дело;
- **вход по Face ID / Touch ID** после первого входа (токен в Keychain, плагин biometric auth);
- **приём файлов из «Поделиться»** (Share Extension) и открытие PDF/DOCX из «Файлов»;
- офлайн-просмотр скачанных документов, виджет или ярлыки «Новое дело».

**Шаги:** `npm i @capacitor/core @capacitor/ios` → `npx cap init "Konsiliér AI" com.konsilier.app` → приложение грузит
https://konsilier.com (server.url) плюс нативные плагины выше → `npx cap add ios` → сборка в Xcode → TestFlight →
отправка на проверку. В описании для проверяющих явно перечислить нативные функции. Цифровые покупки внутри
приложения Apple требует проводить через In-App Purchase; оплату юридических услуг переводом лучше не показывать
в iOS-версии или согласовать до отправки (правило 3.1).

## 3. Microsoft Store (Windows) — PWABuilder (1–2 дня)

**Нужно от основателя:** аккаунт разработчика Microsoft Partner Center (для компаний — разовый платёж, для частных
лиц сейчас бесплатно).

**Шаги:** pwabuilder.com → адрес konsilier.com → «Package for stores» → Windows → ввести данные из Partner Center
(Package ID, Publisher) → загрузить `.msixbundle` в Partner Center → карточка и скриншоты → отправка. Обёртка — тот же
сайт; push и вход работают, правило «минимальной функциональности» у Microsoft мягче.

## Порядок

1. Google Play (дёшево, быстро, без переделок). 2. Microsoft Store. 3. App Store — после нативных функций.
До этого на iPhone приложение ставится с сайта (страница /app) и получает push с iOS 16.4.
