**[🟡] Безопасность — нет заголовков защиты на konsilier.com и api.konsilier.com**
Факт (`curl -I`): на сайте только `cache-control`, `x-powered-by: Next.js`; на API `server: uvicorn`. Нет Strict-Transport-Security,
Content-Security-Policy / frame-ancestors, X-Frame-Options, X-Content-Type-Options, Referrer-Policy.
Ожидаемый: HSTS (max-age ≥ 1 год), `X-Content-Type-Options: nosniff`, `frame-ancestors 'none'` (сайт можно встроить в чужую страницу —
риск кликджекинга на кнопке оплаты), убрать `x-powered-by`. Удобнее всего — в Caddy.
Метки: bug, major, security
