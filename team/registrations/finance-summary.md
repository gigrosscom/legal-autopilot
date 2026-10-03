# Финансовая справка для заявок (RU / EN)

Ведёт «Документация». Источник всех цифр — `team/finance.md` (финансист, 28–29.09.2026); там же расчёты и ссылки.
Здесь — только то, что можно вставить в анкету. Прогноза выручки в заявках **не даём** (продукт запущен 28.09.2026,
факта нет); если форма требует — пишем «pre-revenue».

Обновлено: 30.09.2026. Курс в расчётах: 1 $ = 520 ₸ (оценка).

## RU

| Показатель | Значение | Основание |
|---|---|---|
| Стадия | Pre-revenue: продукт работает с 28.09.2026, оплат пока нет | факт |
| Инвестиции | 0 ₸, собственные средства основателей | decisions 30.09 |
| Цена | 1 990 ₸ за документ; 9 990 ₸ «Дело под ключ» | код, product.md |
| Маржа документа | ≈ 1 853 ₸ (≈ 93 %): минус эквайринг ~1 %, налог 4 % (упрощёнка — проверить у бухгалтера), ИИ ≈ 38 ₸ | finance.md §2.3 (оценка) |
| Постоянные расходы | ≈ 33–43 тыс. ₸ в месяц (сервер Yandex Cloud в Казахстане, почта, домен) | finance.md §2.6 |
| Безубыточность | 18–24 оплаченных документа в месяц | finance.md §2.6 |
| Главная статья роста расходов | ИИ-модели: чат на бесплатном Gemini выдерживает ~200–600 активных пользователей в день; Claude для документов — лимит $3 в день / $50 в месяц | finance.md §3, decisions 29–30.09 |
| На что нужны кредиты программ | Платный уровень Gemini для чата; Claude через Bedrock для документов; GPU для дообучения Zann | — |

## EN

| Item | Value |
|---|---|
| Stage | Pre-revenue; product live since 28 Sep 2026 |
| Funding | Bootstrapped, USD 0 raised |
| Pricing | KZT 1,990 per document; KZT 9,990 per full case |
| Unit margin | ≈ KZT 1,853 per document (≈ 93%) after payment fees, 4% simplified tax and AI cost (estimate) |
| Fixed costs | ≈ KZT 33–43k per month (≈ USD 65–85): Kazakhstan-hosted server, email, domain |
| Break-even | 18–24 paid documents per month |
| Main cost driver | LLM usage: the free Gemini tier serves ~200–600 daily active users; Claude document drafting is capped at USD 3/day, USD 50/month |
| Use of credits | Paid Gemini for chat, Claude via Amazon Bedrock for documents, GPUs for fine-tuning the Zann model |

Проверить перед подачей: счёт Yandex Cloud за сентябрь (факт постоянных расходов) и ставку эквайринга после
подключения онлайн-оплаты.
