# Вход через Google и Apple — что настроить

Кнопки «Войти через Google» и «Войти через Apple» появляются на странице «Вход» (`/account`) сами, как только
в настройках сервера указаны идентификаторы ниже. Пока их нет — кнопок не видно, всё остальное работает как раньше.

Оба идентификатора публичные (их видит браузер), это не секреты. Секретных ключей для этого способа входа не нужно:
сервер проверяет подпись Google/Apple по их открытым ключам.

## Google

1. Откройте [Google Cloud Console](https://console.cloud.google.com/) и выберите (или создайте) проект Konsiliér AI.
2. «APIs & Services» → «OAuth consent screen»: заполните название (Konsiliér AI), почту поддержки, ссылку на сайт,
   политику конфиденциальности и условия. Тип — External. Нужны только стандартные разрешения: email, profile, openid.
   Опубликуйте экран («Publish app»), иначе войти смогут только тестовые пользователи.
3. «APIs & Services» → «Credentials» → «Create credentials» → «OAuth client ID».
4. Тип приложения — **Web application**, название — например, «Konsiliér web».
5. «Authorized JavaScript origins» — добавьте два адреса:
   - `https://konsilier.com`
   - `https://www.konsilier.com`

   («Authorized redirect URIs» оставьте пустым — перенаправления не используются.)
6. Нажмите «Create» и скопируйте **Client ID** (вид `1234567890-abc….apps.googleusercontent.com`).
   Client secret не нужен — никуда его не вставляйте.
7. В настройках сервера (файл `.env` / переменные окружения API) укажите:
   `GOOGLE_CLIENT_ID=<скопированный Client ID>` и перезапустите API.

## Apple

1. Нужна платная учётная запись **Apple Developer Program** (99 $ в год): <https://developer.apple.com/programs/>.
2. [developer.apple.com/account](https://developer.apple.com/account) → «Certificates, Identifiers & Profiles» →
   «Identifiers».
3. Если App ID ещё нет: «+» → «App IDs» → создайте, например, `com.konsilier.app` и включите в нём
   «Sign in with Apple».
4. «+» → **«Services IDs»** → описание «Konsiliér AI», идентификатор, например, `com.konsilier.web` → «Register».
5. Откройте созданный Services ID, включите **«Sign in with Apple»** → «Configure»:
   - Primary App ID — App ID из шага 3;
   - «Domains and Subdomains»: `konsilier.com` (и `www.konsilier.com`, если сайт открывается и так);
   - «Return URLs»: `https://konsilier.com/account`.

   Сохраните («Next» → «Done» → «Continue» → «Save»).
6. В настройках сервера укажите: `APPLE_SERVICES_ID=com.konsilier.web` (ваш Services ID) и перезапустите API.
   `APPLE_REDIRECT_URI` можно не задавать — по умолчанию это `https://konsilier.com/account`
   (адрес сайта из `PUBLIC_SITE_URL` + `/account`); если меняете, он должен совпадать с Return URL из шага 5.

Приватный ключ Apple («Keys», файл `.p8`) для этого входа **не нужен**: сервер проверяет только подписанный Apple
токен. Если человек выбрал «Скрыть e-mail», Apple даст адрес вида `…@privaterelay.appleid.com` — это нормально.

## Проверка

Откройте `https://konsilier.com/account`: вверху «Способов входа» должны появиться кнопки. Войдите — в блоке
подтверждённых данных появится «Google» или «Apple ID» с почтой. Повторный вход тем же аккаунтом Google/Apple с
другого устройства открывает тот же личный кабинет.
