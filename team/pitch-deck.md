# Pitch deck Konsiliér AI (EN, 8 слайдов)

Бэклог №33. Подготовил маркетолог 29.09.2026. Для заявки в NVIDIA Inception (`grants/nvidia-inception.md`, раздел 4)
и для программ Anthropic и AWS Activate (бэклог №26).

**Статус: черновик.** Никуда не отправлен. Подача любой заявки — только после записи «подать» в `decisions.md`.

**Правила этого текста.**
- Каждая цифра — из метрик сервера, из кода продукта или из источника со ссылкой. Источники — в таблице в конце.
- `[[…]]` — заполняет владелец. Без этих полей презентацию не отправляем.
- Konsiliér AI — IT-сервис, а не юридическая помощь. Результат дела не обещаем.
- Визуал: строгий минимализм, фирменные цвета продукта, реальные скриншоты. Без Фемиды, весов, молотков и стоковых
  фото. Формат 16:9. Шрифт — как на сайте.

---

## Slide 1. Problem

**Title:** Everyday legal problems go unsolved because the first step is too hard

- People face small but painful disputes: a refund for a faulty product, unpaid wages, a loan taken out in their name
  by fraudsters, a traffic fine, child support.
- A lawyer is often too expensive for a small claim, so many people do nothing.
- Those who try do not know what to write, where to file it or by what deadline.
- Generic chatbots answer confidently but can cite laws that do not exist or no longer apply.

**Visual:** four short "situation" cards in a row (refund, wages, fraudulent loan, fine), each with one line of
plain text. No numbers on this slide: we have no sourced figure for how many disputes go unresolved.

---

## Slide 2. Solution

**Title:** Konsiliér AI: understand your situation, then act

- An AI assistant for everyday legal questions. It is an IT service, not a law firm, and it does not promise an outcome.
- A free chat explains the situation in plain Russian or Kazakh.
- The AI cites a statute only after it opens the official text on adilet.zan.kz, and it shows the link.
- When the user is ready, the service prepares the document, shows where to file it and reminds them of deadlines.
- If self-service is not enough, the case can be handed to a lawyer from the catalogue, who signs in with a Kazakhstan digital signature.

**Visual:** one horizontal flow with four steps: "Describe → Understand → Document → File and track". Under
"Understand", a small adilet.zan.kz link chip.

---

## Slide 3. Product (live at konsilier.com)

**Title:** What works today

- **Free AI chat** with a daily limit of 40 messages per person. It currently runs on Google Gemini.
- **20 Kazakhstan scenarios**, each carried through to a finished document. Examples: consumer refund, air ticket,
  non-delivery, unpaid wages, dismissal, credit fraud, debt collectors, fine appeal, child support, rental deposit,
  utility billing, road accident.
- **Filing guidance and deadline reminders** for each scenario. Every document is marked as prepared by an IT service,
  and the user is asked to check the details before filing.
- **Telegram bot** that takes a case step by step (description, questions, document, filing, deadlines) in Russian
  and Kazakh.
- **Lawyer directory and sign-up** with digital-signature (NCALayer) verification. Interface in Russian, Kazakh,
  English, Turkish and Arabic.

**Visual:** three real screenshots side by side: the chat with an adilet link, a finished document, and the step
map with deadlines. Take them from the live site, not mock-ups. Caption: "konsilier.com, September 2026".

---

## Slide 4. Market

**Title:** Kazakhstan first: a country that is already online

- Population: **20.5 million** on 1 January 2026 (Bureau of National Statistics).
- **19.5 million internet users**, 93.4% penetration, at the end of 2025 (DataReportal, Digital 2026: Kazakhstan).
- **16.9 million social media user identities** in October 2025 (same source). Our acquisition runs on organic
  social, referrals and lawyers.
- Two languages, Russian and Kazakh, are covered from day one.
- Next: the engine is country-agnostic, with data packs per country. 13 countries are planned (Central Asia, the
  Caucasus, Turkey, the Gulf, North Africa); none of them is live yet.

**Visual:** a map of Kazakhstan with three large numbers: 20.5M, 19.5M, 16.9M. Put the source under each number in
small type. A muted row of the 13 planned countries below, labelled "planned".

*Not included on purpose:* market size in tenge and the number of disputes per year. We have no verified source
yet. Candidate: court statistics at [sud.gov.kz](https://sud.gov.kz/rus/kategoriya/statisticheskie-dannye-sudov),
to be checked before use.

---

## Slide 5. Business model

**Title:** Free to understand, paid to act

- **Free:** chat with the AI assistant, with a daily limit.
- **Paid documents:** from KZT 1,990 per scenario document. It is a fixed price in all 20 Kazakhstan scenarios.
- **Lawyer subscriptions:** paid from day one, no free period. Pro is listed on the site at KZT 15,000–25,000
  per month. `[[Final price after the owner's decision, backlog #17]]`
- 0% commission on lawyers' fees.
- Payment: Kaspi bank transfer is being connected now. Online card payments come after the company account opens.

**Visual:** three columns: "Free: chat", "Per document: from KZT 1,990", "Lawyers: monthly subscription". No revenue
forecast on this slide.

---

## Slide 6. Traction

**Title:** Launched on 28 September 2026: day one

- The product went live on 28 September 2026: web app, PWA and Telegram bot.
- Server metrics on 29 September, 05:00 Almaty time: **5** app visitors, **3** users who started a case, **3**
  lawyer applications, **0** paid customers. We have only just started.
- Built before launch: 20 Kazakhstan scenarios carried through to a finished document, statute checks against the
  official portal, lawyer verification by digital signature.
- Next 30 days: growth through a referral programme, organic social media and lawyer partnerships, with a
  marketing budget of KZT 0.
- `[[Replace with the latest metrics on the date of submission]]`

**Visual:** a simple timeline from 28.09 to today with the live metrics as a small table. Do not show a chart until
there are at least two weeks of data.

---

## Slide 7. Team

**Title:** A lean team, with AI in both the product and the operations

- `[[Founder name]]`, Founder & CEO — `[[one line of relevant experience]]`.
- `[[Developer name, role]]`. Inception requires at least one employed developer.
- `[[Other team members or advisors, e.g. a practising lawyer who reviews scenarios]]`.
- Operations run with six AI agent roles: project manager, marketing, content, client support, lawyer sales and
  finance. Each role reports to the founder twice a day, and the founder approves every spend, publication and
  outbound message.

**Visual:** founder photo and short bio. Next to it, a small diagram of six agent roles around the founder. Use
real photos only; if there is no photo, use initials.

---

## Slide 8. Ask

**Title:** What we are asking for

- **NVIDIA Inception:** cloud credits to test self-hosted open models on NVIDIA GPUs for three steps: redacting
  personal data in Russian and Kazakh, routing messages to the right scenario, and statute search. DLI training for
  the team.
- **Anthropic:** API credits to run Claude in the chat and in document drafting. Claude is off in production until
  then; today we use the free Gemini tier.
- **AWS Activate:** credits for Amazon Bedrock (the provider layer already supports it) and for hosting.
- Why it matters: the free model tier handles only a few hundred active users per day (our estimate), while our
  month-one goal is 100,000 users.
- Contact: `[[firstname.lastname]]@konsilier.com` · konsilier.com

**Visual:** three blocks, one per programme, each with one line on "what we will use it for". No credit amounts:
fill them in from each programme's official terms when submitting. `[[amounts]]`

---

## Источники цифр

| Цифра | Источник | Проверено |
|---|---|---|
| 20 495 975 человек на 01.01.2026 | Бюро национальной статистики, [«Численность населения РК на 1 января 2026 г.»](https://stat.gov.kz/upload/iblock/f87/q1o3ubabjrclwu257mb42t3o5t53acbw/%D0%92-18-06-%D0%9A%20(I%202026)%20%D1%80%D1%83%D1%81.pdf), опубликовано 13.02.2026 | 29.09.2026, PDF открыт |
| 19,5 млн интернет-пользователей, 93,4 %; 16,9 млн аккаунтов в соцсетях (октябрь 2025) | [DataReportal, Digital 2026: Kazakhstan](https://datareportal.com/reports/digital-2026-kazakhstan) | 29.09.2026, страница открыта |
| Лимит чата 40 сообщений в сутки | `apps/api/konsilier/config.py:55` (`chat_daily_limit`) | 29.09.2026 |
| 20 сценариев KZ, 1 990 ₸ в каждом | `packs/kz/scenarios/*.yaml` (`pricing: fixed, amount: 1990`) | 29.09.2026 |
| Pro 15 000–25 000 ₸/мес, 0 % с гонорара | `apps/web/lib/lawyerText/ru.ts:3, 18` | 29.09.2026 |
| 5 языков интерфейса | `apps/web/lib/dict/` (ru, kk, en, tr, ar) | 29.09.2026 |
| Метрики 29.09, 05:00 | `reports/2026-09-29-am.md` (сервер) | 29.09.2026 |
| «Несколько сотен активных в день» на бесплатном Gemini | `finance.md` §3: 200–600, оценка | оценка, проверить |
| Запуск 28.09.2026 | задача владельца на 29.09 | — |

## Что нужно от владельца до отправки

1. Поля `[[…]]`: команда, разработчик в штате, рабочая почта (не info@, см. `grants/nvidia-inception.md` §1).
2. Цена подписки юристов (бэклог №17). До решения на слайде 5 — цена с сайта.
3. Какие заявки уже поданы (Anthropic, AWS, NVIDIA), чтобы не подать дважды (бэклог №26).
4. Логотип и 3 скриншота с сайта. Из среды команды сайт konsilier.com может быть закрыт прокси.
5. Перед отправкой — обновить слайд 6 свежими метриками.
6. Запись «подать заявку» в `decisions.md`.

Сборка в PDF — после ответов владельца. Текст выше — единственный источник для слайдов.
