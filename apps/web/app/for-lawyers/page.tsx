"use client";

import { useEffect, useMemo, useState } from "react";
import { ApiError, api, errorText } from "@/lib/api";
import { FieldError, useFieldErrorText } from "@/components/FieldError";
import {
  KZ_CITIES, LAWYER_KINDS, apiFieldErrors, checkCity, checkEmail, checkFullName, checkLicense, clean, normalizeKzPhone, only,
} from "@/lib/formRules";
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
          <div key={k} className="rounded-xl bg-surface p-3">
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

type FormState = {
  full_name: string; kind: string; organization: string; license_number: string; city: string; phone: string;
  email: string; message: string; website: string;
};

function validate(f: FormState, consent: boolean): Record<string, string> {
  const [, phoneErr] = normalizeKzPhone(f.phone);
  return only({
    full_name: checkFullName(f.full_name),
    kind: LAWYER_KINDS.includes(f.kind) ? null : "required",
    license_number: checkLicense(f.license_number, f.kind),
    city: checkCity(f.city),
    phone: phoneErr,
    email: checkEmail(f.email),
    consent: consent ? null : "required",
  });
}

function ApplyForm() {
  const L = useText().form;
  const [form, setForm] = useState<FormState>({
    full_name: "", kind: "", organization: "", license_number: "", city: "", phone: "", email: "", message: "", website: "",
  });
  const [consent, setConsent] = useState(false);
  const [wantsExpert, setWantsExpert] = useState(false);
  const [spec, setSpec] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [touched, setTouched] = useState<Record<string, boolean>>({});
  const [submitted, setSubmitted] = useState(false);
  const [serverErrors, setServerErrors] = useState<Record<string, string>>({});
  const [done, setDone] = useState<{ referral_code: string; linked?: boolean } | null>(null);
  const [ref, setRef] = useState<string | null>(null);
  const [hasEcp, setHasEcp] = useState<boolean | null>(null);
  const t = useT();
  const errText = useFieldErrorText();
  useEffect(() => {
    api<{ has_ecp: boolean }>("/v1/lawyer/me").then((m) => setHasEcp(m.has_ecp)).catch(() => setHasEcp(false));
  }, []);
  // Read ?ref= after mount (no Suspense needed, so the page prerenders fully and shows instantly).
  useEffect(() => setRef(new URLSearchParams(window.location.search).get("ref")), []);

  const link = useMemo(
    () => (done && typeof window !== "undefined" ? `${window.location.origin}/for-lawyers?ref=${done.referral_code}` : ""),
    [done],
  );
  const errors = useMemo(() => ({ ...validate(form, consent), ...serverErrors }), [form, consent, serverErrors]);
  const shown = (k: string) => ((submitted || touched[k]) && errors[k]) || null;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitted(true);
    setError(null);
    const local = validate(form, consent);
    if (Object.keys(local).length) {
      setError(t("formErrors.fix"));
      document.getElementById(`lf-${Object.keys(local)[0]}`)?.focus();
      return;
    }
    setBusy(true);
    try {
      // sent with the session token: if the lawyer signed in with ЭЦП, the application carries who they are
      const [phone] = normalizeKzPhone(form.phone);
      const out = await api<{ referral_code: string; linked?: boolean }>("/v1/lawyer-applications", {
        method: "POST",
        body: JSON.stringify({ ...form, full_name: clean(form.full_name), city: clean(form.city), phone, consent,
          country: "KZ", specializations: spec, referred_by: ref, wants_expert: wantsExpert }),
      });
      setDone(out);
    } catch (err) {
      const fields = err instanceof ApiError ? apiFieldErrors(err.detail) : null;
      if (fields && Object.keys(fields).length) {
        setServerErrors(fields);
        const [k, code] = Object.entries(fields)[0];
        setError(k === "phone" || k === "ecp" ? errText(k, code) : t("formErrors.fix"));
      } else if (err instanceof ApiError && err.code === "too_many") {
        setError(t("formErrors.too_many"));
      } else {
        setError(errorText(err));
      }
    } finally {
      setBusy(false);
    }
  }

  if (done) {
    return (
      <div className="space-y-4">
        <div className="card space-y-2">
          <h3 className="text-xl font-semibold">{L.doneTitle}</h3>
          <p className="text-sm text-muted">{done.linked ? L.linked : t("lawyer.steps.doneLead")}</p>
        </div>
        <LawyerSteps s={{ applied: true, hasEcp: hasEcp === true || !!done.linked, status: "new" }} />
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

  const set = (k: keyof FormState) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => {
    setForm({ ...form, [k]: e.target.value });
    setError(null);
    if (serverErrors[k]) setServerErrors((x) => Object.fromEntries(Object.entries(x).filter(([f]) => f !== k)));
  };
  const blur = (k: string) => () => setTouched((x) => ({ ...x, [k]: true }));
  const aria = (k: string) => ({
    id: `lf-${k}`, "aria-invalid": !!shown(k), "aria-describedby": shown(k) ? `lf-${k}-err` : undefined, onBlur: blur(k),
  });
  const cls = (k: string) => `input mt-1 ${shown(k) ? "border-danger" : ""}`;
  const licenseLabel = form.kind === "advocate" ? L.licenseAdvocate : form.kind === "legal_consultant" ? L.licenseConsultant
    : form.kind === "human_rights" ? L.licenseOptional : L.license;

  return (
    <form onSubmit={submit} noValidate className="card space-y-3">
      <h3 className="text-xl font-semibold">{L.title}</h3>
      {ref && <p className="chip bg-brand-50 text-brand-dark">{L.invited}</p>}
      {hasEcp === true && <p className="chip bg-brand-50 text-brand-dark">{t("lawyer.ecpOk")}</p>}
      {hasEcp === false && (
        <p className="rounded-xl bg-info-50 p-3 text-sm text-info">
          {t("lawyer.ecpNeeded")} <a className="link font-semibold" href="/account?method=ecp&next=/for-lawyers%23apply">{t("lawyer.ecpSignIn")}</a>
        </p>
      )}
      <label className="block text-sm font-medium">{L.name}
        <input className={cls("full_name")} autoComplete="name" value={form.full_name} onChange={set("full_name")} {...aria("full_name")} />
        <FieldError id="lf-full_name-err" field="full_name" code={shown("full_name")} />
      </label>
      <label className="block text-sm font-medium">{L.kind}
        <select className={cls("kind")} value={form.kind} onChange={set("kind")} {...aria("kind")}>
          <option value="" disabled>{L.kindPick}</option>
          {L.kinds.map(([k, label]) => <option key={k} value={k}>{label}</option>)}
        </select>
        <FieldError id="lf-kind-err" field="kind" code={shown("kind")} />
      </label>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block text-sm font-medium">{licenseLabel}
          <input className={cls("license_number")} value={form.license_number} onChange={set("license_number")} {...aria("license_number")} />
          <FieldError id="lf-license_number-err" field="license_number" code={shown("license_number")} />
        </label>
        <label className="block text-sm font-medium">{L.org}
          <input className={cls("organization")} autoComplete="organization" value={form.organization} onChange={set("organization")} {...aria("organization")} />
        </label>
        <label className="block text-sm font-medium">{L.city}
          <input className={cls("city")} list="lf-cities" autoComplete="address-level2" value={form.city} onChange={set("city")} {...aria("city")} />
          <datalist id="lf-cities">{KZ_CITIES.map((c) => <option key={c} value={c} />)}</datalist>
          <FieldError id="lf-city-err" field="city" code={shown("city")} />
        </label>
        <label className="block text-sm font-medium">{L.phone}
          <input className={cls("phone")} type="tel" inputMode="tel" autoComplete="tel" placeholder="+7 7XX XXX XX XX"
            value={form.phone} onChange={set("phone")} {...aria("phone")} />
          {shown("phone") ? <FieldError id="lf-phone-err" field="phone" code={shown("phone")} />
            : <span className="mt-1 block text-xs font-normal text-muted">{L.phoneHint}</span>}
        </label>
        <label className="block text-sm font-medium sm:col-span-2">{L.email}
          <input className={cls("email")} type="email" inputMode="email" autoComplete="email" value={form.email} onChange={set("email")} {...aria("email")} />
          <FieldError id="lf-email-err" field="email" code={shown("email")} />
        </label>
      </div>
      {/* honeypot: people never see or fill it */}
      <input type="text" name="website" tabIndex={-1} autoComplete="off" aria-hidden="true" value={form.website}
        onChange={set("website")} className="absolute -left-[9999px] h-px w-px opacity-0" />
      <div className="flex flex-wrap gap-2">
        {L.specs.map(([k, label]) => (
          <button
            type="button"
            key={k}
            aria-pressed={spec.includes(k)}
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
      <div>
        <label className="flex min-h-11 cursor-pointer items-start gap-2 py-1 text-sm">
          <input id="lf-consent" type="checkbox" className="mt-0.5 h-5 w-5 shrink-0 accent-brand" checked={consent}
            aria-invalid={!!shown("consent")} aria-describedby={shown("consent") ? "lf-consent-err" : undefined}
            onChange={(e) => setConsent(e.target.checked)} />
          <span>{L.consent} <a className="link" href="/terms">{t("legal.terms")}</a></span>
        </label>
        <FieldError id="lf-consent-err" field="consent" code={shown("consent")} />
      </div>
      <button className="btn-primary w-full py-3 text-base" disabled={busy}>{busy ? L.busy : L.submit}</button>
      {error && <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-danger">{error}</p>}
      <p className="text-xs text-muted">{L.privacy}</p>
    </form>
  );
}

export default function ForLawyers() {
  const L = useText();
  return (
    <div>
      {/* HERO */}
      <section className="grid gap-10 pt-4 pb-14 md:grid-cols-[1.3fr_1fr] md:items-center md:pt-8 md:pb-20 lg:pb-24">
        <div className="space-y-6">
          <span className="chip bg-brand-50 text-brand-dark">{L.hero.chip}</span>
          <h1 className="text-[36px] leading-[1.1] font-semibold tracking-[-0.02em] text-balance md:text-[48px] md:leading-[1.08]">{L.hero.title}</h1>
          <p className="lead">{L.hero.sub}</p>
          <div className="flex flex-wrap gap-3">
            <a href="#apply" className="btn-primary btn-lg">{L.hero.apply}</a>
            <a href="/lawyers" className="btn-ghost btn-lg">{L.hero.rating}</a>
          </div>
          <p className="text-[15px] text-muted">{L.hero.perks}</p>
        </div>
        <DossierPreview />
      </section>

      {/* BENEFITS */}
      <section className="band section-y space-y-10">
        <h2 className="h-section text-balance">{L.benefitsTitle}</h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {L.benefits.map(([icon, title, text, soon]) => (
            <div key={title} className="card space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-50 text-brand"><Icon name={icon as IconName} /></span>
                <h3 className="text-[19px] font-semibold tracking-[-0.012em]">{title}</h3>
                {soon && <span className="chip bg-warning-50 text-warning">{L.soon}</span>}
              </div>
              <p className="text-[17px] leading-[1.47] text-muted">{text}</p>
            </div>
          ))}
        </div>
      </section>

      {/* PARTNER PROGRAMME */}
      <section className="section-y space-y-6">
        <h2 className="h-section text-balance">{L.partner.title}</h2>
        <p className="lead max-w-3xl">{L.partner.intro}</p>
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
        <div className="space-y-3 rounded-[18px] bg-ink p-6 text-white md:p-8">
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
      <section className="band section-y space-y-6">
        <h2 className="h-section text-balance">{L.pricing.title}</h2>
        <p className="rounded-[18px] bg-brand-50 px-5 py-4 text-[15px] font-medium text-brand-dark">{L.pricing.pilot}</p>
        <div className="grid gap-4 md:grid-cols-3">
          <div className="card space-y-2">
            <h3 className="font-semibold">{L.pricing.basic}</h3>
            <div className="text-lg font-semibold">{L.pricing.basicPrice}</div>
            <p className="text-sm text-muted">{L.pricing.basicText}</p>
          </div>
          <div className="card space-y-2 border-brand ring-2 ring-brand/20">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="font-semibold">Pro</h3>
              <span className="chip bg-brand text-white">{L.pricing.proChip}</span>
            </div>
            <div className="text-2xl font-semibold">{L.proPrice}</div>
            <p className="text-sm text-muted">{L.pricing.proText}</p>
          </div>
          <div className="card space-y-2">
            <h3 className="font-semibold">{L.pricing.ngo}</h3>
            <div className="text-2xl font-semibold">{L.pricing.ngoPrice}</div>
            <p className="text-sm text-muted">{L.pricing.ngoText}</p>
          </div>
        </div>
      </section>

      {/* FAQ + FORM */}
      <section id="apply" className="section-y grid scroll-mt-12 gap-8 md:grid-cols-2">
        <div className="order-2 space-y-3">
          <h2 className="h-section text-balance">{L.faqTitle}</h2>
          {L.faq.map(([q, a]) => (
            <details key={q} className="card">
              <summary className="cursor-pointer font-semibold">{q}</summary>
              <p className="mt-2 text-sm text-muted">{a}</p>
            </details>
          ))}
        </div>
        <div className="order-1"><ApplyForm /></div>
      </section>
    </div>
  );
}
