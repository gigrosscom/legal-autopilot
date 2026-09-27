"use client";

import { Suspense, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { publicApi } from "@/lib/api";

// NOTE: commercial terms below are the proposed model (see docs/BUSINESS_MODEL.md) — edit in one place here.
const PRO_PRICE = "15 000–25 000 ₸/мес";

const PAINS = [
  {
    pain: "Клиенты приходят с «меня обманули» и пакетом скриншотов",
    fix: "Вы получаете готовое досье: факты, даты, суммы, доказательства, переписка и хронология — ИИ собрал и проверил их до вас.",
  },
  {
    pain: "Реклама дорогая, сарафан непредсказуем",
    fix: "Дела по вашей специализации и городу приходят сами. Вы выбираете, на какие откликнуться, и называете свою цену.",
  },
  {
    pain: "Клиент пропал после первого этапа и не заплатил",
    fix: "Оплата по этапам через резерв: клиент вносит сумму заранее, вы получаете её сразу после выполнения этапа.",
  },
];

const BENEFITS = [
  { icon: "📂", title: "Готовые дела", text: "Досье вместо первичной консультации — экономия 1–2 часов на каждом клиенте." },
  { icon: "💰", title: "0% с вашего гонорара", text: "Ваша цена — ваши деньги. Сервисный сбор платит клиент за безопасную сделку." },
  { icon: "🔒", title: "Гарантия оплаты", text: "Деньги клиента в резерве до выполнения этапа. Никаких «переведу завтра».", soon: true },
  { icon: "🤖", title: "ИИ-помощник", text: "Черновики исков и жалоб, резюме дела, контроль процессуальных сроков с напоминаниями." },
  { icon: "🏆", title: "Репутация, которую нельзя купить", text: "Рейтинг по доказанным результатам: выигранные дела и возвращённые деньги, а не отзывы друзей." },
  { icon: "👥", title: "Ваши клиенты — ваши", text: "Ведите на платформе и своих клиентов: CRM, сроки, документы. Без комиссии для приведённых вами." },
];

const FAQ = [
  {
    q: "Сколько платформа берёт с юриста?",
    a: "С гонорара — 0%. Базовый тариф бесплатный. Pro (без лимита откликов, приоритет, ИИ-инструменты, CRM) — " + PRO_PRICE + ". Для программы «Основатели» Pro бесплатно 12 месяцев.",
  },
  {
    q: "Кто может присоединиться?",
    a: "Адвокаты, юридические консультанты — члены палаты, правозащитные организации. Статус проверяем по реестрам, личность — через ЭЦП.",
  },
  {
    q: "А адвокатская тайна и этика?",
    a: "Персональные данные клиента скрыты до заключения договора: вы видите обезличенную карточку дела. Договор заключаете вы с клиентом напрямую, платформа — технологический посредник.",
  },
  {
    q: "Правозащитникам тоже платить?",
    a: "Нет. Для НКО и pro bono — бесплатно навсегда, с отчётами о помощи для доноров и грантодателей.",
  },
];

function Calculator() {
  const [cases, setCases] = useState(8);
  const [check, setCheck] = useState(60000);
  const hours = cases * 1.5;
  const income = cases * check;
  return (
    <div className="card space-y-4">
      <h3 className="text-lg font-semibold">Посчитайте для себя</h3>
      <label className="block text-sm">
        Новых дел в месяц через платформу: <b>{cases}</b>
        <input type="range" min={1} max={40} value={cases} onChange={(e) => setCases(+e.target.value)} className="w-full accent-[#1f6f5c]" />
      </label>
      <label className="block text-sm">
        Средний гонорар за дело: <b>{check.toLocaleString("ru-RU")} ₸</b>
        <input type="range" min={10000} max={500000} step={5000} value={check} onChange={(e) => setCheck(+e.target.value)} className="w-full accent-[#1f6f5c]" />
      </label>
      <div className="grid grid-cols-2 gap-3 text-center">
        <div className="rounded-xl bg-brand/10 p-3">
          <div className="text-2xl font-bold text-brand">{income.toLocaleString("ru-RU")} ₸</div>
          <div className="text-xs text-ink/60">дополнительный доход в месяц, без комиссии с гонорара</div>
        </div>
        <div className="rounded-xl bg-ink/5 p-3">
          <div className="text-2xl font-bold">{hours.toLocaleString("ru-RU")} ч</div>
          <div className="text-xs text-ink/60">сэкономлено на первичном разборе (≈1,5 ч на дело)</div>
        </div>
      </div>
      <p className="text-xs text-ink/50">Иллюстративный расчёт по вашим вводным, не обещание дохода.</p>
    </div>
  );
}

function DossierPreview() {
  return (
    <div className="card space-y-3 text-sm">
      <div className="flex items-center justify-between">
        <span className="chip bg-brand/10 text-brand">Новое дело · Защита прав потребителей</span>
        <span className="text-xs text-ink/50">пример</span>
      </div>
      <h3 className="text-base font-semibold">Возврат 180 000 ₸ за недоставленный диван (маркетплейс)</h3>
      <dl className="grid grid-cols-2 gap-2">
        {[
          ["Город", "Алматы"],
          ["Сумма требований", "180 000 ₸"],
          ["Дата оплаты", "15.08.2026"],
          ["Доказательства", "чек, скриншот заказа, переписка"],
          ["Уже сделано", "претензия продавцу подана 01.09"],
          ["Ответ продавца", "отказ (срок истёк)"],
        ].map(([k, v]) => (
          <div key={k} className="rounded-lg bg-ink/5 p-2">
            <dt className="text-xs text-ink/50">{k}</dt>
            <dd className="font-medium">{v}</dd>
          </div>
        ))}
      </dl>
      <p className="text-xs text-ink/60">ФИО и контакты клиента откроются после заключения договора.</p>
      <div className="flex flex-wrap gap-2">
        <button className="btn-primary" disabled>Откликнуться: моя цена</button>
        <button className="btn-ghost" disabled>Задать вопрос клиенту</button>
      </div>
    </div>
  );
}

function ShareCard({ name, demo }: { name: string; demo: boolean }) {
  return (
    <div className="mx-auto w-full max-w-sm rounded-3xl bg-gradient-to-br from-[#1f6f5c] to-[#14213d] p-5 text-white shadow-lg">
      <div className="text-xs uppercase tracking-widest opacity-70">
        Konsilier.AI · {demo ? "пример карточки" : "юрист-основатель"}
      </div>
      <div className="mt-3 text-xl font-bold">{demo ? "Айгерим Н." : name}</div>
      <div className="text-sm opacity-80">Защита прав потребителей · Алматы</div>
      {demo ? (
        <div className="mt-4 flex items-end justify-between">
          <div>
            <div className="text-4xl font-bold">84</div>
            <div className="text-xs opacity-70">рейтинг по доказанным результатам</div>
          </div>
          <div className="text-right text-sm">
            <div><b>134</b> дела</div>
            <div><b>71 млн ₸</b> возвращено</div>
          </div>
        </div>
      ) : (
        <div className="mt-4 text-sm opacity-90">
          ⭐ Основатель платформы. Рейтинг по доказанным результатам появится после первых завершённых дел.
        </div>
      )}
      <div className="mt-4 rounded-xl bg-white/10 p-2 text-center text-xs">konsilier.com · запись к юристу</div>
    </div>
  );
}

function ApplyForm() {
  const params = useSearchParams();
  const [form, setForm] = useState({
    full_name: "", kind: "advocate", organization: "", license_number: "", city: "", contact: "", message: "",
  });
  const [spec, setSpec] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<{ referral_code: string } | null>(null);
  const ref = params.get("ref");

  const link = useMemo(
    () => (done && typeof window !== "undefined" ? `${window.location.origin}/for-lawyers?ref=${done.referral_code}` : ""),
    [done],
  );
  const shareText = `Присоединяюсь к Konsilier.AI — платформе, где юристы получают готовые дела с досье, 0% комиссии с гонорара и оплату по этапам. Программа «Основатели»: Pro бесплатно 12 месяцев. `;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const out = await publicApi<{ referral_code: string }>("/v1/lawyer-applications", {
        method: "POST",
        body: JSON.stringify({ ...form, country: "KZ", specializations: spec, referred_by: ref }),
      });
      setDone(out);
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  if (done) {
    return (
      <div className="card space-y-4">
        <h3 className="text-xl font-bold">Заявка принята 🎉</h3>
        <p className="text-sm text-ink/70">
          Мы проверим статус и свяжемся с вами. Пока — ваша личная ссылка. Каждый коллега, который присоединится по ней,
          даёт вам и ему +3 месяца Pro, а первые 10 приглашённых поднимают вас в ранней выдаче дел.
        </p>
        <div className="flex gap-2">
          <input className="input" readOnly value={link} onFocus={(e) => e.target.select()} />
          <button className="btn-ghost" onClick={() => navigator.clipboard?.writeText(link)}>Копировать</button>
        </div>
        <div className="flex flex-wrap gap-2">
          <a className="btn-primary" target="_blank" rel="noreferrer" href={`https://wa.me/?text=${encodeURIComponent(shareText + link)}`}>WhatsApp</a>
          <a className="btn-primary" target="_blank" rel="noreferrer" href={`https://t.me/share/url?url=${encodeURIComponent(link)}&text=${encodeURIComponent(shareText)}`}>Telegram</a>
          <a className="btn-ghost" target="_blank" rel="noreferrer" href={`https://www.linkedin.com/sharing/share-offsite/?url=${encodeURIComponent(link)}`}>LinkedIn</a>
        </div>
        <ShareCard name={form.full_name} demo={false} />
      </div>
    );
  }

  const specs = [
    ["consumer", "Защита прав потребителей"],
    ["credit_fraud", "Мошеннические кредиты"],
    ["debt_collectors", "Коллекторы и долги"],
    ["labor", "Трудовые споры"],
    ["family", "Семейные дела"],
    ["business", "Бизнес и дебиторка"],
  ];
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setForm({ ...form, [k]: e.target.value });

  return (
    <form onSubmit={submit} className="card space-y-3">
      <h3 className="text-xl font-bold">Стать юристом-основателем</h3>
      {ref && <p className="chip bg-brand/10 text-brand">Вас пригласил коллега · +3 месяца Pro</p>}
      <input className="input" required minLength={3} placeholder="ФИО" value={form.full_name} onChange={set("full_name")} />
      <select className="input" value={form.kind} onChange={set("kind")}>
        <option value="advocate">Адвокат</option>
        <option value="legal_consultant">Юридический консультант</option>
        <option value="human_rights">Правозащитная организация / НКО</option>
        <option value="other">Другое</option>
      </select>
      <div className="grid gap-3 sm:grid-cols-2">
        <input className="input" placeholder="Коллегия / палата / организация" value={form.organization} onChange={set("organization")} />
        <input className="input" placeholder="Номер лицензии / удостоверения" value={form.license_number} onChange={set("license_number")} />
        <input className="input" placeholder="Город" value={form.city} onChange={set("city")} />
        <input className="input" required minLength={3} placeholder="Телефон, Telegram или e-mail" value={form.contact} onChange={set("contact")} />
      </div>
      <div className="flex flex-wrap gap-2">
        {specs.map(([k, label]) => (
          <button
            type="button"
            key={k}
            onClick={() => setSpec(spec.includes(k) ? spec.filter((s) => s !== k) : [...spec, k])}
            className={`chip px-3 py-1.5 ${spec.includes(k) ? "bg-brand text-white" : ""}`}
          >
            {label}
          </button>
        ))}
      </div>
      <textarea className="input" rows={2} placeholder="Что для вас важно в платформе? (необязательно)" value={form.message} onChange={set("message")} />
      <button className="btn-primary w-full py-3 text-base" disabled={busy}>{busy ? "…" : "Подать заявку"}</button>
      {error && <p className="text-sm text-red-600">{error}</p>}
      <p className="text-xs text-ink/50">Проверяем статус по реестрам. Данные используем только для проверки и связи с вами.</p>
    </form>
  );
}

export default function ForLawyers() {
  return (
    <div className="space-y-16">
      {/* HERO */}
      <section className="grid gap-8 pt-4 md:grid-cols-[1.3fr_1fr] md:items-center">
        <div className="space-y-5">
          <span className="chip bg-brand/10 text-brand">Для адвокатов, юристов и правозащитников</span>
          <h1 className="text-3xl font-bold leading-tight md:text-4xl">
            Клиенты приходят к вам с готовым делом. Вы занимаетесь правом — а не поиском клиентов и бумагами.
          </h1>
          <p className="text-lg text-ink/70">
            ИИ собирает факты и доказательства, платформа гарантирует оплату по этапам, а ваш рейтинг строится на реальных
            выигранных делах. 0% с вашего гонорара.
          </p>
          <div className="flex flex-wrap gap-3">
            <a href="#apply" className="btn-primary px-6 py-3 text-base">Стать основателем — бесплатно</a>
            <a href="/lawyers" className="btn-ghost px-6 py-3 text-base">Как выглядит рейтинг</a>
          </div>
          <p className="text-sm text-ink/60">Первые 100 юристов — Pro бесплатно на 12 месяцев и значок «Основатель».</p>
        </div>
        <DossierPreview />
      </section>

      {/* PAINS → FIX */}
      <section className="space-y-4">
        <h2 className="text-2xl font-bold">Знакомо?</h2>
        <div className="grid gap-4 md:grid-cols-3">
          {PAINS.map((p) => (
            <div key={p.pain} className="card space-y-2">
              <p className="text-sm text-red-700">✗ {p.pain}</p>
              <p className="text-sm">✓ {p.fix}</p>
            </div>
          ))}
        </div>
      </section>

      {/* BENEFITS */}
      <section className="space-y-4">
        <h2 className="text-2xl font-bold">Что вы получаете</h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {BENEFITS.map((b) => (
            <div key={b.title} className="card space-y-2">
              <div className="flex items-center gap-2">
                <span className="text-2xl">{b.icon}</span>
                <h3 className="font-semibold">{b.title}</h3>
                {b.soon && <span className="chip bg-amber-100 text-amber-900">скоро</span>}
              </div>
              <p className="text-sm text-ink/70">{b.text}</p>
            </div>
          ))}
        </div>
      </section>

      {/* CALCULATOR + SHARE CARD */}
      <section className="grid gap-6 md:grid-cols-2 md:items-center">
        <Calculator />
        <div className="space-y-3">
          <h2 className="text-2xl font-bold">Ваша репутация — ваш актив</h2>
          <p className="text-ink/70">
            Карточка с рейтингом по доказанным результатам — ваша цифровая визитка. Делитесь ей в Instagram, Telegram и
            LinkedIn: клиенты записываются к вам напрямую, без комиссии.
          </p>
          <ShareCard name="" demo />
        </div>
      </section>

      {/* GROWTH LOOP */}
      <section className="space-y-4">
        <h2 className="text-2xl font-bold">Растите вместе с платформой</h2>
        <div className="grid gap-4 md:grid-cols-4">
          {[
            ["🤝", "Пригласите коллегу", "+3 месяца Pro вам и ему. 10 приглашённых — приоритет в выдаче дел."],
            ["📣", "Кейс недели", "ИИ готовит обезличенный пост о вашем выигранном деле — публикуйте в один клик."],
            ["🏅", "Топ месяца", "Лидеры по возвратам в каждой категории и городе — на главной и в наших соцсетях."],
            ["🧾", "Свои клиенты — без комиссии", "Приглашайте своих клиентов по личной ссылке: CRM, сроки и документы бесплатно."],
          ].map(([icon, title, text]) => (
            <div key={title} className="card space-y-1">
              <div className="text-2xl">{icon}</div>
              <h3 className="font-semibold">{title}</h3>
              <p className="text-sm text-ink/70">{text}</p>
            </div>
          ))}
        </div>
      </section>

      {/* PRICING */}
      <section className="space-y-4">
        <h2 className="text-2xl font-bold">Тарифы</h2>
        <div className="grid gap-4 md:grid-cols-3">
          <div className="card space-y-2">
            <h3 className="font-semibold">Базовый</h3>
            <div className="text-2xl font-bold">0 ₸</div>
            <p className="text-sm text-ink/70">Профиль, проверка статуса, отклики на дела (лимит в месяц), рейтинг.</p>
          </div>
          <div className="card space-y-2 border-brand ring-2 ring-brand/20">
            <div className="flex items-center gap-2">
              <h3 className="font-semibold">Pro</h3>
              <span className="chip bg-brand text-white">Основателям 12 мес. бесплатно</span>
            </div>
            <div className="text-2xl font-bold">{PRO_PRICE}</div>
            <p className="text-sm text-ink/70">Без лимита откликов, приоритет в выдаче, ИИ-черновики, контроль сроков, CRM своих клиентов.</p>
          </div>
          <div className="card space-y-2">
            <h3 className="font-semibold">Правозащитникам и НКО</h3>
            <div className="text-2xl font-bold">0 ₸ навсегда</div>
            <p className="text-sm text-ink/70">Pro-функции для pro bono и отчёты о помощи для доноров.</p>
          </div>
        </div>
      </section>

      {/* FAQ + FORM */}
      <section id="apply" className="grid gap-6 md:grid-cols-2">
        <div className="space-y-3">
          <h2 className="text-2xl font-bold">Вопросы</h2>
          {FAQ.map((f) => (
            <details key={f.q} className="card">
              <summary className="cursor-pointer font-semibold">{f.q}</summary>
              <p className="mt-2 text-sm text-ink/70">{f.a}</p>
            </details>
          ))}
        </div>
        <Suspense>
          <ApplyForm />
        </Suspense>
      </section>
    </div>
  );
}
