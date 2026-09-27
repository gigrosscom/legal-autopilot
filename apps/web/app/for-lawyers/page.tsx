"use client";

import { useEffect, useMemo, useState } from "react";
import { publicApi, errorText } from "@/lib/api";
import { Icon, type IconName } from "@/components/ui";
import { useLang } from "@/lib/i18n";
import { lawyerText, type LawyerText } from "@/lib/lawyerText";

// NOTE: commercial terms below are the proposed model (see docs/BUSINESS_MODEL.md) — edit them here, in both languages.
// Kazakh copy is kept short so it fits on narrow phones.
type Text = LawyerText;

function useText(): Text {
  const { lang } = useLang();
  return lawyerText(lang);
}

function Calculator() {
  const L = useText().calc;
  const [cases, setCases] = useState(8);
  const [check, setCheck] = useState(60000);
  const hours = cases * 1.5;
  const income = cases * check;
  return (
    <div className="card space-y-4">
      <h3 className="text-lg font-semibold">{L.title}</h3>
      <label className="block text-sm">
        {L.cases}: <b>{cases}</b>
        <input type="range" min={1} max={40} value={cases} onChange={(e) => setCases(+e.target.value)} className="h-8 w-full accent-[#1f6f5c]" />
      </label>
      <label className="block text-sm">
        {L.fee}: <b>{check.toLocaleString("ru-RU")} ₸</b>
        <input type="range" min={10000} max={500000} step={5000} value={check} onChange={(e) => setCheck(+e.target.value)} className="h-8 w-full accent-[#1f6f5c]" />
      </label>
      <div className="grid grid-cols-2 gap-3 text-center">
        <div className="rounded-xl bg-brand-50 p-3">
          <div className="text-xl font-bold text-brand sm:text-2xl">{income.toLocaleString("ru-RU")} ₸</div>
          <div className="text-xs text-muted">{L.income}</div>
        </div>
        <div className="rounded-xl bg-sand p-3">
          <div className="text-xl font-bold sm:text-2xl">{hours.toLocaleString("ru-RU")} {L.hoursUnit}</div>
          <div className="text-xs text-muted">{L.hours}</div>
        </div>
      </div>
      <p className="text-xs text-muted">{L.note}</p>
    </div>
  );
}

function DossierPreview() {
  const L = useText().dossier;
  return (
    <div className="card space-y-3 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="chip bg-brand-50 text-brand-dark">{L.chip}</span>
        <span className="text-xs text-muted">{L.example}</span>
      </div>
      <p className="text-base font-semibold">{L.title}</p>
      <dl className="grid grid-cols-2 gap-2">
        {L.rows.map(([k, v]) => (
          <div key={k} className="rounded-lg bg-sand p-2">
            <dt className="text-xs text-muted">{k}</dt>
            <dd className="font-medium">{v}</dd>
          </div>
        ))}
      </dl>
      <p className="text-xs text-muted">{L.hidden}</p>
      <div className="flex flex-wrap gap-2">
        <button className="btn-primary" disabled>{L.respond}</button>
        <button className="btn-ghost" disabled>{L.ask}</button>
      </div>
    </div>
  );
}

function ShareCard({ name, demo }: { name: string; demo: boolean }) {
  const L = useText().card;
  return (
    <div className="mx-auto w-full max-w-sm rounded-3xl bg-gradient-to-br from-[#1f6f5c] to-[#14213d] p-5 text-white shadow-lg">
      <div className="text-xs uppercase tracking-widest opacity-70">
        Konsilier.AI · {demo ? L.sample : L.partner}
      </div>
      <div className="mt-3 text-xl font-bold">{demo ? "Айгерим Н." : name}</div>
      <div className="text-sm opacity-80">{L.spec}</div>
      {demo ? (
        <div className="mt-4 flex items-end justify-between">
          <div>
            <div className="text-4xl font-bold">84</div>
            <div className="text-xs opacity-70">{L.score}</div>
          </div>
          <div className="text-end text-sm">
            <div><b>134</b> {L.cases}</div>
            <div><b>71 {L.mln} ₸</b> {L.recovered}</div>
          </div>
        </div>
      ) : (
        <div className="mt-4 text-sm opacity-90">{L.pending}</div>
      )}
      <div className="mt-4 rounded-xl bg-white/10 p-2 text-center text-xs">{L.footer}</div>
    </div>
  );
}

function ApplyForm() {
  const L = useText().form;
  const [form, setForm] = useState({
    full_name: "", kind: "advocate", organization: "", license_number: "", city: "", contact: "", message: "",
  });
  const [wantsExpert, setWantsExpert] = useState(false);
  const [spec, setSpec] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<{ referral_code: string } | null>(null);
  const [ref, setRef] = useState<string | null>(null);
  // Read ?ref= after mount (no Suspense needed, so the page prerenders fully and shows instantly).
  useEffect(() => setRef(new URLSearchParams(window.location.search).get("ref")), []);

  const link = useMemo(
    () => (done && typeof window !== "undefined" ? `${window.location.origin}/for-lawyers?ref=${done.referral_code}` : ""),
    [done],
  );

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const out = await publicApi<{ referral_code: string }>("/v1/lawyer-applications", {
        method: "POST",
        body: JSON.stringify({ ...form, country: "KZ", specializations: spec, referred_by: ref, wants_expert: wantsExpert }),
      });
      setDone(out);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  if (done) {
    return (
      <div className="card space-y-4">
        <h3 className="text-xl font-bold">{L.doneTitle}</h3>
        <p className="text-sm text-muted">{L.doneText}</p>
        <div className="flex flex-col gap-2 sm:flex-row">
          <input className="input" readOnly value={link} onFocus={(e) => e.target.select()} />
          <button className="btn-ghost shrink-0" onClick={() => navigator.clipboard?.writeText(link)}>{L.copy}</button>
        </div>
        <div className="flex flex-wrap gap-2">
          <a className="btn-primary" target="_blank" rel="noreferrer" href={`https://wa.me/?text=${encodeURIComponent(L.share + link)}`}>WhatsApp</a>
          <a className="btn-primary" target="_blank" rel="noreferrer" href={`https://t.me/share/url?url=${encodeURIComponent(link)}&text=${encodeURIComponent(L.share)}`}>Telegram</a>
          <a className="btn-ghost" target="_blank" rel="noreferrer" href={`https://www.linkedin.com/sharing/share-offsite/?url=${encodeURIComponent(link)}`}>LinkedIn</a>
        </div>
        <ShareCard name={form.full_name} demo={false} />
      </div>
    );
  }

  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setForm({ ...form, [k]: e.target.value });

  return (
    <form onSubmit={submit} className="card space-y-3">
      <h3 className="text-xl font-bold">{L.title}</h3>
      {ref && <p className="chip bg-brand-50 text-brand-dark">{L.invited}</p>}
      <input className="input" required minLength={3} aria-label={L.name} placeholder={L.name} value={form.full_name} onChange={set("full_name")} />
      <select className="input" aria-label={L.kind} value={form.kind} onChange={set("kind")}>
        {L.kinds.map(([k, label]) => <option key={k} value={k}>{label}</option>)}
      </select>
      <div className="grid gap-3 sm:grid-cols-2">
        <input className="input" aria-label={L.org} placeholder={L.org} value={form.organization} onChange={set("organization")} />
        <input className="input" aria-label={L.license} placeholder={L.license} value={form.license_number} onChange={set("license_number")} />
        <input className="input" aria-label={L.city} placeholder={L.city} value={form.city} onChange={set("city")} />
        <input className="input" required minLength={3} aria-label={L.contact} placeholder={L.contact} value={form.contact} onChange={set("contact")} />
      </div>
      <div className="flex flex-wrap gap-2">
        {L.specs.map(([k, label]) => (
          <button
            type="button"
            key={k}
            onClick={() => setSpec(spec.includes(k) ? spec.filter((s) => s !== k) : [...spec, k])}
            className={`chip min-h-10 px-3 py-2 text-sm ${spec.includes(k) ? "bg-brand text-white" : ""}`}
          >
            {label}
          </button>
        ))}
      </div>
      <label className="flex items-start gap-2 text-sm">
        <input type="checkbox" className="mt-0.5 h-5 w-5 shrink-0 accent-brand" checked={wantsExpert} onChange={(e) => setWantsExpert(e.target.checked)} />
        <span>{L.expert}</span>
      </label>
      <textarea className="input" rows={2} aria-label={L.message} placeholder={L.message} value={form.message} onChange={set("message")} />
      <button className="btn-primary w-full py-3 text-base" disabled={busy}>{busy ? L.busy : L.submit}</button>
      {error && <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-danger">{error}</p>}
      <p className="text-xs text-muted">{L.privacy}</p>
    </form>
  );
}

export default function ForLawyers() {
  const L = useText();
  return (
    <div className="space-y-16">
      {/* HERO */}
      <section className="grid gap-8 pt-4 md:grid-cols-[1.3fr_1fr] md:items-center">
        <div className="space-y-5">
          <span className="chip bg-brand-50 text-brand-dark">{L.hero.chip}</span>
          <h1 className="text-3xl font-bold leading-tight md:text-4xl">{L.hero.title}</h1>
          <p className="text-lg text-muted">{L.hero.sub}</p>
          <div className="flex flex-wrap gap-3">
            <a href="#apply" className="btn-primary px-6 py-3 text-base">{L.hero.apply}</a>
            <a href="/lawyers" className="btn-ghost px-6 py-3 text-base">{L.hero.rating}</a>
          </div>
          <p className="text-sm text-muted">{L.hero.perks}</p>
        </div>
        <DossierPreview />
      </section>

      {/* PAINS → FIX */}
      <section className="space-y-4">
        <h2 className="text-2xl font-bold">{L.painsTitle}</h2>
        <div className="grid gap-4 md:grid-cols-3">
          {L.pains.map(([pain, fix]) => (
            <div key={pain} className="card space-y-2">
              <p className="flex gap-2 text-sm text-danger"><Icon name="x" size={18} className="mt-0.5" />{pain}</p>
              <p className="flex gap-2 text-sm"><Icon name="check" size={18} className="mt-0.5 text-brand" />{fix}</p>
            </div>
          ))}
        </div>
      </section>

      {/* BENEFITS */}
      <section className="space-y-4">
        <h2 className="text-2xl font-bold">{L.benefitsTitle}</h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {L.benefits.map(([icon, title, text, soon]) => (
            <div key={title} className="card space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-50 text-brand"><Icon name={icon as IconName} /></span>
                <h3 className="font-semibold">{title}</h3>
                {soon && <span className="chip bg-warning-50 text-warning">{L.soon}</span>}
              </div>
              <p className="text-sm text-muted">{text}</p>
            </div>
          ))}
        </div>
      </section>

      {/* CALCULATOR + SHARE CARD */}
      <section className="grid gap-6 md:grid-cols-2 md:items-center">
        <Calculator />
        <div className="space-y-3">
          <h2 className="text-2xl font-bold">{L.reputationTitle}</h2>
          <p className="text-muted">{L.reputation}</p>
          <ShareCard name="" demo />
        </div>
      </section>

      {/* GROWTH LOOP */}
      <section className="space-y-4">
        <h2 className="text-2xl font-bold">{L.growthTitle}</h2>
        <div className="grid gap-4 md:grid-cols-4">
          {L.growth.map(([icon, title, text]) => (
            <div key={title} className="card space-y-1">
              <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-50 text-brand"><Icon name={icon as IconName} /></span>
              <h3 className="font-semibold">{title}</h3>
              <p className="text-sm text-muted">{text}</p>
            </div>
          ))}
        </div>
      </section>

      {/* PARTNER PROGRAMME */}
      <section className="space-y-4">
        <h2 className="text-2xl font-bold">{L.partner.title}</h2>
        <p className="text-muted">{L.partner.intro}</p>
        <div className="grid gap-4 md:grid-cols-2">
          <div className="card space-y-2">
            <h3 className="font-semibold">{L.partner.doesTitle}</h3>
            <ul className="list-inside list-disc space-y-1 text-sm text-muted">
              {L.partner.does.map((x) => <li key={x}>{x}</li>)}
            </ul>
          </div>
          <div className="card space-y-2 border-brand ring-2 ring-brand/20">
            <h3 className="font-semibold">{L.partner.getsTitle}</h3>
            <ul className="list-inside list-disc space-y-1 text-sm text-muted">
              {L.partner.gets.map((x) => <li key={x}>{x}</li>)}
            </ul>
          </div>
        </div>
        <p className="text-xs text-muted">{L.partner.lose}</p>
        <div className="space-y-3 rounded-2xl bg-ink p-5 text-white shadow-sm">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-lg font-semibold">{L.expert.title}</h3>
            <span className="chip bg-white/15 text-white">{L.expert.chip}</span>
          </div>
          <p className="text-sm text-white/80">{L.expert.intro}</p>
          <div className="grid gap-4 md:grid-cols-2">
            <ul className="list-inside list-disc space-y-1 text-sm text-white/80">
              <li className="list-none font-semibold text-white">{L.expert.doesTitle}</li>
              {L.expert.does.map((x) => <li key={x}>{x}</li>)}
            </ul>
            <ul className="list-inside list-disc space-y-1 text-sm text-white/80">
              <li className="list-none font-semibold text-white">{L.expert.getsTitle}</li>
              {L.expert.gets.map((x) => <li key={x}>{x}</li>)}
            </ul>
          </div>
        </div>
      </section>

      {/* PRICING */}
      <section className="space-y-4">
        <h2 className="text-2xl font-bold">{L.pricing.title}</h2>
        <div className="grid gap-4 md:grid-cols-3">
          <div className="card space-y-2">
            <h3 className="font-semibold">{L.pricing.basic}</h3>
            <div className="text-2xl font-bold">0 ₸</div>
            <p className="text-sm text-muted">{L.pricing.basicText}</p>
          </div>
          <div className="card space-y-2 border-brand ring-2 ring-brand/20">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="font-semibold">Pro</h3>
              <span className="chip bg-brand text-white">{L.pricing.proChip}</span>
            </div>
            <div className="text-2xl font-bold">{L.proPrice}</div>
            <p className="text-sm text-muted">{L.pricing.proText}</p>
          </div>
          <div className="card space-y-2">
            <h3 className="font-semibold">{L.pricing.ngo}</h3>
            <div className="text-2xl font-bold">{L.pricing.ngoPrice}</div>
            <p className="text-sm text-muted">{L.pricing.ngoText}</p>
          </div>
        </div>
      </section>

      {/* FAQ + FORM */}
      <section id="apply" className="grid gap-6 md:grid-cols-2">
        <div className="space-y-3">
          <h2 className="text-2xl font-bold">{L.faqTitle}</h2>
          {L.faq.map(([q, a]) => (
            <details key={q} className="card">
              <summary className="cursor-pointer font-semibold">{q}</summary>
              <p className="mt-2 text-sm text-muted">{a}</p>
            </details>
          ))}
        </div>
        <ApplyForm />
      </section>
    </div>
  );
}
