"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { EmergencyPanel } from "@/components/EmergencyPanel";
import { Alert, Button, Icon } from "@/components/ui";
import { ApiError, api, errorText, publicApi, type CaseView, type Emergency } from "@/lib/api";
import { FieldError } from "@/components/FieldError";
import { apiFieldErrors, checkEmail, checkFullName, clean, normalizeKzPhone, only } from "@/lib/formRules";
import { useLang, useT } from "@/lib/i18n";
import { TERMS_VERSION } from "@/lib/legal/terms";

/**
 * «Обратиться» to a lawyer: one short form registers the case (the story) and the applicant's contacts.
 * Direct booking opens with payments; until then the team passes the case to a lawyer from the directory.
 */
export default function LawyerRequestPage() {
  const t = useT();
  const { lang } = useLang();
  const [lawyer, setLawyer] = useState<{ id: string | null; name: string | null }>({ id: null, name: null });
  const [story, setStory] = useState("");
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [emergency, setEmergency] = useState<Emergency | null>(null);
  const [done, setDone] = useState<string | null>(null);
  // the case is created once: a retry after a wrong phone must not register the story twice
  const [caseId, setCaseId] = useState<string | null>(null);
  const [touched, setTouched] = useState<Record<string, boolean>>({});
  const [serverErrors, setServerErrors] = useState<Record<string, string>>({});
  const errors = { ...only({ full_name: checkFullName(name), phone: normalizeKzPhone(phone)[1], email: checkEmail(email) }),
    ...serverErrors };
  const shown = (k: string) => (touched[k] && errors[k]) || null;
  const blur = (k: string) => () => setTouched((x) => ({ ...x, [k]: true }));

  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    setLawyer({ id: q.get("lawyer"), name: q.get("name") });
  }, []);

  async function submit(e: React.FormEvent, skipTriage = false) {
    e.preventDefault();
    setTouched({ full_name: true, phone: true, email: true });
    if (Object.keys(errors).length) return;
    setBusy(true); setError(null);
    try {
      if (!skipTriage) {
        const tri = await publicApi<{ emergency: boolean; message: string; numbers: Emergency["numbers"] }>(
          "/v1/triage", { method: "POST", body: JSON.stringify({ text: story, country: "KZ", language: lang }) });
        if (tri.emergency) { setEmergency({ message: tri.message, numbers: tri.numbers }); return; }
      }
      let id = caseId;
      if (!id) {
        const out = await api<{ case: CaseView }>("/v1/cases", {
          method: "POST", body: JSON.stringify({ text: story.trim(), language: lang, country: "KZ", accept_terms: TERMS_VERSION }) });
        id = out.case.id;
        setCaseId(id);
      }
      await api(`/v1/cases/${id}/lawyer-request`, { method: "POST", body: JSON.stringify({
        lawyer_ref: lawyer.id, full_name: clean(name), phone: normalizeKzPhone(phone)[0] ?? phone.trim(),
        email: email.trim() || null, consent }) });
      setDone(id);
      window.scrollTo({ top: 0 });
    } catch (err) {
      const fields = err instanceof ApiError ? apiFieldErrors(err.detail) : null;
      if (fields && Object.keys(fields).length) {
        setServerErrors(fields);
        setTouched({ full_name: true, phone: true, email: true });
        setError(t("formErrors.fix"));
      } else setError(errorText(err));
    } finally { setBusy(false); }
  }

  if (done) {
    return (
      <div className="mx-auto max-w-xl space-y-4">
        <Alert tone="info" icon="checkCircle" title={t("request.doneTitle")}>{t("request.doneText")}</Alert>
        <Button href={`/case/${done}`} size="lg" className="w-full" iconEnd="arrowRight">{t("request.proceed")}</Button>
        <p className="text-sm text-muted">{t("request.continueHint")}</p>
      </div>
    );
  }

  const ready = story.trim().length >= 10 && name.trim().length >= 2 && phone.trim().length > 0 && consent;
  const input = (k: string, set: (v: string) => void) => ({
    className: `${field} ${shown(k) ? "border-danger" : ""}`, onBlur: blur(k), "aria-invalid": !!shown(k),
    "aria-describedby": shown(k) ? `rq-${k}-err` : undefined,
    onChange: (e: React.ChangeEvent<HTMLInputElement>) => {
      set(e.target.value);
      if (serverErrors[k]) setServerErrors((x) => Object.fromEntries(Object.entries(x).filter(([f]) => f !== k)));
    },
  });
  const field = "input mt-1 min-h-12 text-base";
  return (
    <form onSubmit={submit} noValidate className="mx-auto max-w-xl space-y-5">
      <Link href="/lawyers" className="inline-flex items-center gap-1 text-sm text-muted hover:text-brand">
        <Icon name="arrowRight" size={16} className="rotate-180 rtl:rotate-0" />{t("request.back")}
      </Link>
      <div className="space-y-2">
        <h1 className="text-3xl font-semibold tracking-tight">{t("request.title")}</h1>
        {lawyer.name && <p className="flex items-center gap-2 font-medium"><Icon name="lawyer" className="text-brand" />{lawyer.name}</p>}
        <p className="text-muted">{t("request.lead")}</p>
      </div>

      <label className="block text-sm font-semibold">{t("request.story")}
        <textarea className="input mt-1 min-h-36 text-base font-normal" required minLength={10} value={story}
          onChange={(e) => setStory(e.target.value)} placeholder={t("start.placeholder")} />
      </label>
      <fieldset className="space-y-3">
        <legend className="text-sm font-semibold">{t("request.contacts")}</legend>
        <label className="block text-sm">{t("request.name")}
          <input required autoComplete="name" value={name} {...input("full_name", setName)} />
          <FieldError id="rq-full_name-err" field="full_name" code={shown("full_name")} />
        </label>
        <label className="block text-sm">{t("request.phone")}
          <input required type="tel" inputMode="tel" autoComplete="tel" placeholder="+7 700 000 00 00"
            value={phone} {...input("phone", setPhone)} />
          <FieldError id="rq-phone-err" field="phone" code={shown("phone")} />
        </label>
        <label className="block text-sm">{t("request.email")}
          <input type="email" inputMode="email" autoComplete="email" value={email} {...input("email", setEmail)} />
          <FieldError id="rq-email-err" field="email" code={shown("email")} />
        </label>
      </fieldset>
      <label className="flex items-start gap-3 text-sm">
        <input type="checkbox" className="mt-1 h-5 w-5 shrink-0" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
        <span>{t("request.consent")} <Link href="/terms" className="link">{t("legal.terms")}</Link></span>
      </label>

      {emergency && <EmergencyPanel info={emergency} onContinue={() => { setEmergency(null); submit(new Event("submit") as unknown as React.FormEvent, true); }} />}
      {error && <Alert tone="danger" role="alert">{error}</Alert>}
      <Button size="lg" className="w-full" disabled={busy || !ready} icon={busy ? "spinner" : "send"}>{t("request.submit")}</Button>
      <p className="text-xs text-muted">{t("request.note")}</p>
    </form>
  );
}
