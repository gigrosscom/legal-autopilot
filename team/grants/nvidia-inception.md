# NVIDIA Inception: заявка Konsiliér AI (финальная форма)

Финансист. Первая версия 28.09.2026, форма портала разобрана 29.09.2026, финальная редакция 30.09.2026.
**Ведёт «Документация» с 30.09.2026**; тексты сверены с решениями владельца (без юристов и подписок).
**Заявка не подана.** Подаёт владелец лично и только после записи «подать заявку в NVIDIA Inception» в
`decisions.md`.

Что изменилось 30.09.2026:
- требования программы перепроверены на официальной странице (раздел 1);
- юрлицо взято из кода продукта: ТОО «Konsilier AI», БИН 260940036818, зарегистрировано 29.09.2026, Алматы
  (`apps/web/lib/legal/terms.ts`). **Расхождение:** в `decisions.md` от 29.09.2026 записано «Регистрация ТОО
  откладывается». Владельцу подтвердить, что ТОО зарегистрировано (раздел 5, п. 1);
- все поля формы заполнены окончательными ответами. Пустые места `[владелец]` — только данные, которые знает
  один владелец;
- из текстов убраны формулировки, которых нельзя обещать: «verified lawyer», «reviewed template», «scenarios are
  lawyer-checked». Сценарии юристом не проверены; юристов на платформе нет (решение 28–30.09).

---

## 0. Коротко

| Вопрос | Ответ |
|---|---|
| Это грант деньгами? | **Нет.** Inception — бесплатная программа поддержки: курсы DLI, скидки, доступ к кредитам партнёров и к инвесторам. Денег на счёт нет |
| Сколько стоит? | 0: «no application fees, membership fees, or equity requirements» |
| Срок подачи? | Нет: «no application fees, deadlines, or cohorts» |
| Что блокирует подачу сейчас | Только «да» владельца. Сотрудников 2, почты dev@ и saltanat@, PDF, регистрация ТОО — готово 30.09 |
| Что реально даёт деньги на ИИ | Облачные кредиты партнёров (раздел 6): быстрее всего Google Cloud (Gemini) и AWS Activate Founders |

---

## 1. Условия программы (проверено 30.09.2026)

Источник: FAQ на [nvidia.com/en-us/startups](https://www.nvidia.com/en-us/startups/), открыт 30.09.2026.

| Требование (цитата) | Konsiliér AI |
|---|---|
| «Members must employ at least one developer, maintain a working website, be officially incorporated, and be less than 10 years old.» | Разработчик: основатель сам пишет код (`docs/nvidia-inception-application.md`: «Founder, developer»). Засчитает ли NVIDIA основателя как «employed developer», не сказано, **проверить**. Сайт: https://konsilier.com. Юрлицо: ТОО, 2026 |
| «Your company needs to be incorporated, and you'll need to provide the incorporation date when you apply.» | Дата регистрации: 29.09.2026 (`terms.ts`), подтвердить справкой |
| Кого не берут: консалтинг и заказная разработка, крипто, облачные провайдеры, реселлеры и дистрибьюторы, публичные компании | Не про нас |
| Презентация: «A pitch deck helps us understand your company's mission, solutions, and unique value in the market.» | Текст слайдов — `team/pitch-deck.md`; английская презентация — артефакт, указанный в `docs/nvidia-inception-application.md`. Нужен PDF |
| Ограничений по странам на странице нет; отдельный контакт только для Китая | Казахстан не запрещён. Список «embargoed» стран в коде портала (29.09.2026): Belarus, Cuba, Iran, North Korea, Russian Federation, Syria |

**Правила портала, которых нет на публичной странице.** Прочитаны из JS-кода
[programs.nvidia.com/phoenix/application](https://programs.nvidia.com/phoenix/application) 29.09.2026. 30.09.2026
портал открывается, но код формы подгружается только после входа, поэтому повторно правила не проверены. Это не
опубликованные правила, они могут измениться:
- **автоотказ, если «Number of employees» меньше 2** («No other staff/developers»);
- автоотказ, если сайт не открывается, компания старше 10 лет, статус «Publicly Held», «In IPO Registration»,
  «Out of Business», «Acquired», или страна из списка эмбарго;
- вход только по рабочей почте. Бесплатные домены (gmail, mail.ru, yandex и т. п.) и **общие ящики** (`info@`,
  `admin@`, `support@`, `contact@`, `hello@`, `team@`, `ai@`, `ceo@`, `founder@`, `sales@`, `marketing@`)
  запрещены. **`info@konsilier.com` не подойдёт**, хотя `docs/nvidia-inception-application.md` советует именно его;
- второй контакт обязателен; его почта — на том же домене и не общий ящик.

Сроки рассмотрения NVIDIA не публикует («We'll reach out with more information after we review your
application»).

---

## 2. Форма: поле → ответ (вставлять как есть)

Порядок: вход → Contact Information → Company Information → Workloads & Industries → согласие с условиями →
Submit. Поля, которые портал заполнит сам по адресу сайта, проверить и исправить.

### Вход

| Поле | Ответ |
|---|---|
| Business Email | dev@konsilier.com (владелец 30.09: n.khabibulla@ заблокирован Google; info@ портал не принимает) |

### Шаг 1. Contact Information

| Поле | Ответ |
|---|---|
| Primary contact — First name | Nurlan (сверить написание с паспортом) |
| Primary contact — Last name | Khabibulla (сверить написание с паспортом) |
| Primary contact — Job title | Founder & CTO (владелец, 30.09) |
| Primary contact — Email | подставится из входа |
| Secondary contact — First name / Last name | Saltanat / Tulegenova (сверить написание с удостоверением) |
| Secondary contact — Job title | CEO (руководитель ТОО по справке о регистрации) |
| Secondary contact — Email | saltanat@konsilier.com (владелец, 30.09; ceo@ и info@ портал не принимает) |
| Company website | https://konsilier.com |

Имя основателя — из `docs/nvidia-inception-application.md` («founder and sole participant: Nurlan Khabibulla»).

### Шаг 2. Company Information

| Поле | Ответ |
|---|---|
| Company name | Konsilier AI LLP (ТОО «Konsilier AI»; латиницей — как в справке о регистрации) |
| Headquarters location | Kazakhstan |
| Headquarters state / province | Almaty |
| Company description (200–1 000 символов) | Текст ниже, 851 символов |
| Incorporation year | 2026 |
| Number of employees | 2 (основатель и Салтанат Тулегенова — данные владельца 30.09) |
| Business status | Privately Held (или ближайший вариант для действующей частной компании) |
| Total funding raised (USD) | 0 (инвестиции не привлекали — владелец, 30.09) |
| Investors or incubators | None |
| Company pitch deck | PDF (раздел 4) |
| Referrers | пусто |

**Company description (851 символов, одной строкой, без `>`):**

> Konsiliér AI is an AI assistant for everyday legal questions, live in Kazakhstan since September 2026 at konsilier.com, as an installable web app and a Telegram bot. It is an IT service, not a law firm. A person describes a problem in Russian or Kazakh: a refund for a faulty product, unpaid wages, a loan taken out by fraudsters, a fine. A free chat explains the situation and links each cited statute to its official text on adilet.zan.kz. When a document is needed, the service drafts it from a structured scenario (pre-trial claim, complaint, application), shows where to file it and reminds about deadlines. A document costs KZT 1,990. Personal data is redacted before any model call. A rules engine picks the legal path; the language model writes the text and classifies requests. Next: our own Russian/Kazakh legal model (Zann) on open weights.

### Шаг 3. Workloads & Industries

| Поле | Ответ |
|---|---|
| Workloads | Generative AI / LLMs; Conversational AI; Natural Language Processing; Speech AI, если есть в списке (голосовой ввод работает) |
| Primary industry | «Legal» или «Professional Services», если есть; иначе «Consumer Internet» |
| Target industries | Consumer Internet; Public Sector |

Затем — согласие с условиями программы и Submit. Сделать скриншот подтверждения.

### Тексты для профиля после приёма (EN)

**Product**

> Konsiliér AI (web app, installable PWA, Telegram bot), Kazakhstan.
> - Free AI legal chat with a daily message limit. Cited statutes link to the official text on adilet.zan.kz.
> - 20 published Kazakhstan scenarios (consumer refunds, fraudulent loans, unpaid wages, dismissal, fine appeals,
>   child support, rental deposits and others), each ending in a finished document, plus beta scenarios.
> - Filing instructions for public channels and deadline reminders (e-mail, web push).
> - Document upload: the service reads PDFs, photos and DOCX files and asks only for what is missing.
> - Personal data (names, national ID numbers, phones, addresses) is replaced with placeholders before any model
>   call. Servers and file storage are in Kazakhstan (Yandex Cloud, kz1).
> - Every document is marked as prepared by an IT service; the user checks it before filing.

**How do you use AI today?**

> We do not run our own models or NVIDIA GPUs yet. The chat runs on free Google Gemini models through the API;
> documents are drafted by Anthropic Claude under a daily spend cap.
> One provider layer supports Gemini, Anthropic Claude (direct or Amazon Bedrock) and OpenAI-compatible hosts of
> open models, so models can be swapped without touching the product. The model never chooses the legal path:
> scenarios, deadlines and addressees come from data files; the model writes text and classifies free-text input.

**How do you plan to use NVIDIA technologies?**

> Our main technical goal is Zann, a Russian/Kazakh legal language model adapted from open weights and measured on
> our own benchmark (Zann-Bench). Plan: (1) benchmark current models on Zann-Bench; (2) LoRA fine-tuning of an 8B
> open model for routing, fact extraction and PII detection with NeMo; (3) serve the small model with NVIDIA NIM
> to cut cost per case and keep sensitive steps in Kazakhstan; (4) evaluate Canary/Parakeet for mixed
> Russian-Kazakh speech. We would use Inception cloud credits for these experiments and DLI courses for training.

Факты: `docs/STRATEGY.md` (этапы Zann), `zann/README.md` (бенчмарк: пока 22 задания маршрутизации и 3 извлечения,
юристом не проверены — поэтому не пишем «размеченный юристами»).

**Target customers**

> Individuals in Kazakhstan with everyday disputes who cannot start with a lawyer, and small businesses. Later: Central Asia, the Caucasus, Turkey and MENA through country data packs.

**Traction**

> Launched in September 2026. Early stage: no paying customers yet.

Цифры посещений не пишем: на 30.09.2026 их слишком мало для заявки (7 посетителей, 0 оплат). Когда появятся
метрики, подставить факт с датой.

**What do you need from NVIDIA**

> Cloud credits to benchmark and fine-tune open models, DLI training, and introductions to the VC network when we
> raise a seed round.

---

## 3. One-pager (EN)

> **Konsiliér AI — an AI assistant for everyday legal questions**
> konsilier.com · Almaty, Kazakhstan · launched September 2026 · Konsilier AI LLP
>
> **Problem.** People with everyday disputes (a refund, unpaid wages, a fraudulent loan, a fine) often do nothing:
> a lawyer costs too much for a small claim, and they do not know what to write, to whom or by when.
>
> **Product.** A free AI chat explains the situation and links statutes to their official text. Paid documents
> (KZT 1,990; KZT 9,990 for a full case) come from structured scenarios, with filing instructions and deadline
> reminders. Web, PWA and Telegram; Russian and Kazakh, with English, Turkish
> and Arabic in the interface.
>
> **How it works.** A rules engine chooses the legal path from data files. The language model writes text and
> classifies requests. Personal data is redacted before any model call. Documents are marked as prepared by an IT
> service.
>
> **Business model.** Paid documents, created after payment. The chat is free with a daily limit.
>
> **AI roadmap.** Zann: a Russian/Kazakh legal model adapted from open weights, released only when it beats the
> current model on our benchmark.
>
> **Team.** Nurlan Khabibulla, Founder & CTO (background in law, business and management; built the product).
> Saltanat Tulegenova, CEO (lawyer, student).
> **Funding.** Bootstrapped, USD 0 raised.
> **Traction.** Launched September 2026; no paying customers yet.
> **Contact.** dev@konsilier.com

---

## 4. Презентация

PDF: [deck/Konsilier-AI-pitch-deck.pdf](deck/Konsilier-AI-pitch-deck.pdf), исходник `deck/konsilier-deck.html`.
**Обновлён 30.09.2026 («Документация»)** по решениям владельца: убраны каталог юристов, подписка юристов и
«партнёрства с юристами»; добавлены «Дело под ключ» 9 990 ₸ и загрузка документов; команда — основатель (CTO) и
Салтанат Тулегенова (CEO, юрист, студентка); на последнем слайде просьбы — NVIDIA, Google for Startups, AWS Activate.

---

## 5. Что нужно только от владельца

Сделано 30.09: ТОО зарегистрировано; почты dev@ и saltanat@; 2 сотрудника; LinkedIn; инвестиции 0 / None;
PDF презентации обновлён.

Осталось:
1. Проверить строку о себе: «Background in law, business and management» — верно ли (три диплома — какие?).
2. Написание имён латиницей как в паспорте: Nurlan Khabibulla, Saltanat Tulegenova.
3. Запись в `decisions.md`: «подать заявку в NVIDIA Inception» (очерёдность утверждена, подача — отдельным «да»).

---

## 6. Откуда реально придут кредиты на ИИ

Суммы «до» — это максимум, а не гарантия. Проверено 28.09.2026, 30.09 не перепроверялось.

| Программа | Сколько | Главное условие | Для нас сейчас |
|---|---|---|---|
| NVIDIA Inception | Денег нет | Раздел 1 | Членство — после снятия блокеров |
| Google for Startups Cloud ([cloud.google.com/startup](https://cloud.google.com/startup)) | Pre-funded: $2 000; до $350 000 для AI-first с институциональным раундом | Большой тир — только с инвестором | **Самое полезное**: кредиты покрывают Gemini, на котором работает чат |
| AWS Activate ([aws.amazon.com/startups/credits](https://aws.amazon.com/startups/credits/)) | Founders: $1 000 | Pre-Series B, моложе 10 лет | Реально. Покрытие Claude в Bedrock — проверить |
| Microsoft for Startups ([microsoft.com/startups](https://www.microsoft.com/en-us/startups/)) | до $150 000 постепенно | Растёт с расходами на Azure | Нашего стека там нет |
| Anthropic Startups ([claude.com/programs/startups](https://claude.com/programs/startups)) | Не опубликовано | Нужны инвестиции институционального инвестора | Без инвестора маловероятно |

---

## 7. Как подать (после записи «подать»)

1. Проверить, что всё из раздела 5 готово.
2. Открыть [nvidia.com/en-us/startups](https://www.nvidia.com/en-us/startups/) → Apply Now → портал
   programs.nvidia.com/phoenix/application.
3. Войти личной рабочей почтой, подтвердить код.
4. Заполнить три шага по разделу 2. Всё, что портал подставил сам, проверить.
5. Загрузить PDF, согласиться с условиями, Submit, скриншот подтверждения.
6. Менеджер проекта записывает дату подачи в `decisions.md` и `backlog.md`. Ответ ждать на почте (и в спаме).
7. После приёма: профиль продукта (тексты выше), запросы кредитов партнёров по одному, коды DLI.

## Источники (открыты 30.09.2026, если не указано иное)

- https://www.nvidia.com/en-us/startups/ — FAQ: условия, презентация, стоимость.
- https://programs.nvidia.com/phoenix/application — код формы, прочитан 29.09.2026.
- Продукт (ветка `claude/zealous-volta-a3ipv6`, 30.09.2026): `apps/web/lib/legal/terms.ts`,
  `docs/nvidia-inception-application.md`, `docs/STRATEGY.md`, `zann/README.md`.


## 8. Профиль после подачи (01.10.2026)

Продукт в профиле NVIDIA добавлен владельцем 01.10.2026 (решение: показываем модель, не приложение):
- **Zann** · Model · Developing · Not Accelerated · NVIDIA сейчас не используем;
- рассматриваем: Llama3 8B Instruct NIM, NeMo Framework, NeMo Guardrails, NeMo Retriever, Riva, NeMo Evaluator,
  NeMo Curator, Llama Nemotron, TensorRT for RTX; из не‑NVIDIA — PyTorch.
- Описание (402 знака) и Technical Details (931 знак) — как в сообщении «Документации» 01.10; при обновлении стадии
  (первая версия Zann) — поменять на Alpha/Beta и Accelerated, если запустим на GPU NVIDIA.

Дальше: раздел Benefits — какие партнёрские кредиты на GPU доступны; ответ NVIDIA по заявке — на dev@konsilier.com.

01.10.2026: пришло письмо NVIDIA Training — создан аккаунт **NVIDIA Academy** (обучение/DLI) на Нурлана Хабибуллу. Это не
решение по Inception. NPN (партнёрская сеть реселлеров) нам не относится. Решение Inception ждём отдельным письмом на dev@.
