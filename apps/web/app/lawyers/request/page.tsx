"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { EmergencyPanel } from "@/components/EmergencyPanel";
import { Alert, Button, Icon } from "@/components/ui";
import { api, errorText, publicApi, type CaseView, type Emergency } from "@/lib/api";
import { useLang, useT } from "@/lib/i18n";

/**
 * «Обратиться» to a lawyer: one short form registers the case (the story) and the applicant's contacts.
 * Direct booking opens with payments; until then the team passes the case to a verified lawyer.
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

  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    setLawyer({ id: q.get("lawyer"), name: q.get("name") });
  }, []);

  async function submit(e: React.FormEvent, skipTriage = false) {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      if (!skipTriage) {
        const tri = await publicApi<{ emergency: boolean; message: string; numbers: Emergency["numbers"] }>(
          "/v1/triage", { method: "POST", body: JSON.stringify({ text: story, country: "KZ", language: lang }) });
        if (tri.emergency) { setEmergency({ message: tri.message, numbers: tri.numbers }); return; }
      }
      const out = await api<{ case: CaseView }>("/v1/cases", {
        method: "POST", body: JSON.stringify({ text: story.trim(), language: lang, country: "KZ" }) });
      await api(`/v1/cases/${out.case.id}/lawyer-request`, { method: "POST", body: JSON.stringify({
        lawyer_ref: lawyer.id, full_name: name.trim(), phone: phone.trim(), email: email.trim() || null, consent }) });
      setDone(out.case.id);
      window.scrollTo({ top: 0 });
    } catch (err) {
      setError(errorText(err));
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

  const ready = story.trim().length >= 10 && name.trim().length >= 2 && phone.replace(/\D/g, "").length >= 10 && consent;
  const field = "input mt-1 min-h-12 text-base";
  return (
    <form onSubmit={submit} className="mx-auto max-w-xl space-y-5">
      <Link href="/lawyers" className="inline-flex items-center gap-1 text-sm text-muted hover:text-brand">
        <Icon name="arrowRight" size={16} className="rotate-180 rtl:rotate-0" />{t("request.back")}
      </Link>
      <div className="space-y-2">
        <h1 className="text-3xl font-bold tracking-tight">{t("request.title")}</h1>
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
          <input className={field} required autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="block text-sm">{t("request.phone")}
          <input className={field} required type="tel" inputMode="tel" autoComplete="tel" placeholder="+7 700 000 00 00"
            value={phone} onChange={(e) => setPhone(e.target.value)} />
        </label>
        <label className="block text-sm">{t("request.email")}
          <input className={field} type="email" inputMode="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
      </fieldset>
      <label className="flex items-start gap-3 text-sm">
        <input type="checkbox" className="mt-1 h-5 w-5 shrink-0" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
        <span>{t("request.consent")}</span>
      </label>

      {emergency && <EmergencyPanel info={emergency} onContinue={() => { setEmergency(null); submit(new Event("submit") as unknown as React.FormEvent, true); }} />}
      {error && <Alert tone="danger" role="alert">{error}</Alert>}
      <Button size="lg" className="w-full" disabled={busy || !ready} icon={busy ? "spinner" : "send"}>{t("request.submit")}</Button>
      <p className="text-xs text-muted">{t("request.note")}</p>
    </form>
  );
}
