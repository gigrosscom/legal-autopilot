"use client";

import { useEffect, useMemo, useState } from "react";
import { api, errorText } from "@/lib/api";
import { useT } from "@/lib/i18n";
import { LawyerSteps } from "@/components/LawyerSteps";
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
    </div>
  );
}

function ShareCard({ name, demo }: { name: string; demo: boolean }) {
  const L = useText().card;
  return (
    <div className="mx-auto w-full max-w-sm rounded-3xl bg-gradient-to-br from-brand to-ink p-5 text-white shadow-lg">
      <div className="text-xs uppercase tracking-widest opacity-70">
        Konsiliér AI · {demo ? L.sample : L.partner}
      </div>
      <div className="mt-3 text-xl font-semibold">{demo ? "Айгерим Н." : name}</div>
      <div className="text-sm opacity-80">{L.spec}</div>
      {demo ? (
        <div className="mt-4 flex items-end justify-between">
          <div>
            <div className="text-4xl font-semibold">84</div>
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
  const [hasEcp, setHasEcp] = useState<boolean | null>(null);
  const t = useT();
  useEffect(() => {
    api<{ has_ecp: boolean }>("/v1/lawyer/me").then((m) => setHasEcp(m.has_ecp)).catch(() => setHasEcp(false));
  }, []);
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
      // sent with the session token: if the lawyer signed in with ЭЦП, the application carries who they are
      const out = await api<{ referral_code: string }>("/v1/lawyer-applications", {
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
      <div className="space-y-4">
        <div className="card space-y-2">
          <h3 className="text-xl font-semibold">{L.doneTitle}</h3>
          <p className="text-sm text-muted">{t("lawyer.steps.doneLead")}</p>
        </div>
        <LawyerSteps s={{ applied: true, hasEcp: hasEcp === true, status: "new" }} />
        <a className="link text-sm" href="/lawyer">{t("lawyer.cabinetLink")}</a>
        <div className="card space-y-3">
        <p className="text-sm text-muted">{t("lawyer.steps.share")}</p>
        <div className="flex flex-col gap-2 sm:flex-row">
          <input className="input" readOnly value={link} onFocus={(e) => e.target.select()} />
          <button className="btn-ghost shrink-0" onClick={() => navigator.clipboard?.writeText(link)}>{L.copy}</button>
        </div>
        <div className="flex flex-wrap gap-2">
          <a className="btn-primary" target="_blank" rel="noreferrer" href={`https://wa.me/?text=${encodeURIComponent(L.share + link)}`}>WhatsApp</a>
          <a className="btn-primary" target="_blank" rel="noreferrer" href={`https://t.me/share/url?url=${encodeURIComponent(link)}&text=${encodeURIComponent(L.share)}`}>Telegram</a>
          <a className="btn-ghost" target="_blank" rel="noreferrer" href={`https://www.linkedin.com/sharing/share-offsite/?url=${encodeURIComponent(link)}`}>LinkedIn</a>
        </div>
        </div>
        <ShareCard name={form.full_name} demo={false} />
      </div>
    );
  }

  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setForm({ ...form, [k]: e.target.value });

  return (
    <form onSubmit={submit} className="card space-y-3">
      <h3 className="text-xl font-semibold">{L.title}</h3>
      {ref && <p className="chip bg-brand-50 text-brand-dark">{L.invited}</p>}
      {hasEcp === true && <p className="chip bg-brand-50 text-brand-dark">{t("lawyer.ecpOk")}</p>}
      {hasEcp === false && (
        <p className="rounded-xl bg-info-50 p-3 text-sm text-info">
          {t("lawyer.ecpNeeded")} <a className="link font-semibold" href="/account?method=ecp&next=/for-lawyers%23apply">{t("lawyer.ecpSignIn")}</a>
        </p>
      )}
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
      <label className="flex min-h-11 cursor-pointer items-start gap-2 py-1 text-sm">
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

const H2 = "text-[32px] font-semibold leading-[1.08] tracking-[-0.015em] text-balance text-ink md:text-[48px]";

export default function ForLawyers() {
  const L = useText();
  return (
    <div className="space-y-4 md:space-y-5">
      {/* HERO: centred, large type */}
      <section className="mx-auto max-w-4xl space-y-6 pt-6 pb-10 text-center md:pt-10 md:pb-14">
        <span className="chip bg-brand-50 text-brand-dark">{L.hero.chip}</span>
        <h1 className="text-[40px] font-semibold leading-[1.05] tracking-[-0.015em] text-balance text-ink md:text-[64px]">{L.hero.title}</h1>
        <p className="mx-auto max-w-2xl text-[21px] leading-[1.38] text-muted text-pretty md:text-[24px]">{L.hero.sub}</p>
        <div className="flex flex-wrap justify-center gap-3 pt-2">
          <a href="#apply" className="btn-primary min-h-12 px-7 text-[17px]">{L.hero.apply}</a>
          <a href="/lawyers" className="btn-ghost min-h-12 px-7 text-[17px]">{L.hero.rating}</a>
        </div>
        <p className="text-sm text-muted">{L.hero.perks}</p>
      </section>

      <section className="tile flex justify-center">
        <div className="w-full max-w-xl"><DossierPreview /></div>
      </section>

      {/* BENEFITS */}
      <section className="space-y-10 px-1 py-16 md:py-20">
        <h2 className={`${H2} text-center`}>{L.benefitsTitle}</h2>
        <div className="grid gap-x-8 gap-y-10 sm:grid-cols-2 lg:grid-cols-3">
          {L.benefits.map(([icon, title, text, soon]) => (
            <div key={title} className="space-y-3">
              <Icon name={icon as IconName} size={32} strokeWidth={1.5} className="text-action" />
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="text-[21px] font-semibold tracking-[-0.01em]">{title}</h3>
                {soon && <span className="chip bg-warning-50 text-warning">{L.soon}</span>}
              </div>
              <p className="text-[17px] text-muted">{text}</p>
            </div>
          ))}
        </div>
      </section>

      {/* PARTNER PROGRAMME */}
      <section className="tile space-y-8">
        <div className="mx-auto max-w-3xl space-y-3 text-center">
          <h2 className={H2}>{L.partner.title}</h2>
          <p className="text-[17px] text-muted md:text-[21px]">{L.partner.intro}</p>
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          <div className="card space-y-3 border-0 shadow-none">
            <h3 className="text-[21px] font-semibold">{L.partner.doesTitle}</h3>
            <ul className="list-inside list-disc space-y-1.5 text-[15px] text-muted">
              {L.partner.does.map((x) => <li key={x}>{x}</li>)}
            </ul>
          </div>
          <div className="card space-y-3 border-0 shadow-none ring-2 ring-action">
            <h3 className="text-[21px] font-semibold">{L.partner.getsTitle}</h3>
            <ul className="list-inside list-disc space-y-1.5 text-[15px] text-muted">
              {L.partner.gets.map((x) => <li key={x}>{x}</li>)}
            </ul>
          </div>
        </div>
        <p className="text-center text-xs text-muted">{L.partner.lose}</p>
        <div className="space-y-4 rounded-2xl bg-ink p-7 text-white md:p-10">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-[24px] font-semibold tracking-[-0.01em]">{L.expert.title}</h3>
            <span className="chip bg-white/15 text-white">{L.expert.chip}</span>
          </div>
          <p className="text-[17px] text-white/80">{L.expert.intro}</p>
          <div className="grid gap-4 md:grid-cols-2">
            <ul className="list-inside list-disc space-y-1.5 text-[15px] text-white/80">
              <li className="list-none font-semibold text-white">{L.expert.doesTitle}</li>
              {L.expert.does.map((x) => <li key={x}>{x}</li>)}
            </ul>
            <ul className="list-inside list-disc space-y-1.5 text-[15px] text-white/80">
              <li className="list-none font-semibold text-white">{L.expert.getsTitle}</li>
              {L.expert.gets.map((x) => <li key={x}>{x}</li>)}
            </ul>
          </div>
        </div>
      </section>

      {/* PRICING */}
      <section className="space-y-8 px-1 py-16 md:py-20">
        <div className="mx-auto max-w-3xl space-y-4 text-center">
          <h2 className={H2}>{L.pricing.title}</h2>
          <p className="inline-block rounded-full bg-brand-50 px-4 py-2 text-sm font-medium text-brand-dark">{L.pricing.pilot}</p>
        </div>
        <div className="grid gap-3 md:grid-cols-3">
          <div className="space-y-2 rounded-2xl bg-sand p-7">
            <h3 className="text-[21px] font-semibold">{L.pricing.basic}</h3>
            <div className="text-[28px] font-semibold tracking-[-0.015em]">{L.pricing.basicPrice}</div>
            <p className="text-[15px] text-muted">{L.pricing.basicText}</p>
          </div>
          <div className="space-y-2 rounded-2xl bg-sand p-7 ring-2 ring-action">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="text-[21px] font-semibold">Pro</h3>
              <span className="chip bg-action text-white">{L.pricing.proChip}</span>
            </div>
            <div className="text-[28px] font-semibold tracking-[-0.015em]">{L.proPrice}</div>
            <p className="text-[15px] text-muted">{L.pricing.proText}</p>
          </div>
          <div className="space-y-2 rounded-2xl bg-sand p-7">
            <h3 className="text-[21px] font-semibold">{L.pricing.ngo}</h3>
            <div className="text-[28px] font-semibold tracking-[-0.015em]">{L.pricing.ngoPrice}</div>
            <p className="text-[15px] text-muted">{L.pricing.ngoText}</p>
          </div>
        </div>
      </section>

      {/* FAQ + FORM */}
      <section id="apply" className="tile grid scroll-mt-20 gap-8 md:grid-cols-2">
        <div className="order-2 space-y-4">
          <h2 className="text-[28px] font-semibold tracking-[-0.015em] md:text-[40px]">{L.faqTitle}</h2>
          <div className="divide-y divide-line border-y border-line">
            {L.faq.map(([q, a]) => (
              <details key={q} className="group py-4">
                <summary className="flex cursor-pointer list-none items-center justify-between gap-3 text-[17px] font-semibold [&::-webkit-details-marker]:hidden">
                  {q}<Icon name="chevronDown" size={18} className="shrink-0 text-muted transition-transform group-open:rotate-180" />
                </summary>
                <p className="mt-2 text-[15px] text-muted">{a}</p>
              </details>
            ))}
          </div>
        </div>
        <div className="order-1"><ApplyForm /></div>
      </section>
    </div>
  );
}
