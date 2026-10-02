"use client";

import { useCallback, useEffect, useState } from "react";
import { Alert, Badge, Button, Icon } from "@/components/ui";
import { LawyerCard } from "@/components/LawyerCard";
import { ApiError, api, errorText } from "@/lib/api";
import { useT } from "@/lib/i18n";

type PilotLawyer = {
  id: number; name: string; kind: string; kind_label: string; organization: string; city: string;
  specializations: { key: string; label: string }[]; price: number; currency: string; price_note: string;
};
type LawyerBill = {
  id: number; code: string; purpose: "lawyer"; amount: number; currency: string | null; status: string;
  kaspi_pay_link?: string; company_account?: string; company_name?: string | null;
};
export type PilotRequest = {
  id: number; status: "new" | "accepted" | "declined" | "paid" | "closed"; application_id: number;
  lawyer: { name: string; kind: string } | null; price: number | null; created_at: string;
  invoice: LawyerBill | null; payment_available: boolean;
};
type PilotState = {
  lawyers: PilotLawyer[]; currency: string; request: PilotRequest | null; last: PilotRequest | null;
  payment_available: boolean;
};

export function money(amount: number, currency: string | null | undefined): string {
  return `${amount.toLocaleString("ru-RU").replace(/ /g, " ")} ${currency === "KZT" ? "₸" : currency ?? ""}`.trim();
}

/** «Юрист по кнопке» (closed pilot): choose a pilot lawyer → send a request → the lawyer accepts → pay the lawyer's
 *  price to the company's account → the lawyer gets the case dossier. `onPaid` refreshes the lawyer block. */
export function LawyerPilot({ caseId, onChange }: { caseId: string; onChange?: (status: string | null) => void }) {
  const t = useT();
  const [s, setS] = useState<PilotState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState<number | null>(null);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [consent, setConsent] = useState(false);

  const load = useCallback(() => api<PilotState>(`/v1/cases/${caseId}/lawyers`)
    .then((v) => { setS(v); onChange?.(v.request?.status ?? null); })
    .catch((e) => setError(errorText(e))), [caseId, onChange]);
  useEffect(() => { load(); }, [load]);

  // while the payment is being checked, look again now and then: the lawyer block appears once it is confirmed
  const waiting = s?.request?.invoice?.status === "awaiting_confirmation" || s?.request?.status === "new";
  useEffect(() => {
    if (!waiting) return;
    const timer = setInterval(() => { load(); }, 15000);
    return () => clearInterval(timer);
  }, [waiting, load]);

  async function run(path: string, body?: unknown) {
    setBusy(true);
    setError(null);
    try {
      await api(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
      await load();
      return true;
    } catch (e) {
      if (e instanceof ApiError && e.code === "invalid_request") setError(t("pilot.formError"));
      else if (e instanceof ApiError && e.code === "lawyer_payment_unavailable") setError(t("pilot.payLater"));
      else setError(errorText(e));
      return false;
    } finally { setBusy(false); }
  }

  async function send(appId: number) {
    if (await run(`/v1/cases/${caseId}/lawyer-request`, { application_id: appId, full_name: name, phone, consent })) setOpen(null);
  }

  if (!s) return error ? <Alert tone="danger" role="alert">{error}</Alert> : <p className="text-sm text-muted">{t("common.loading")}</p>;
  const req = s.request;
  const lawyerName = req?.lawyer?.name ?? "";
  const bill = req?.invoice ?? null;

  return (
    <section aria-labelledby="pilot-title" className="space-y-3">
      <div className="card space-y-2">
        <h2 id="pilot-title" className="flex items-center gap-2 font-semibold"><Icon name="lawyer" size={20} className="text-brand" />{t("pilot.title")}</h2>
        <p className="text-sm text-muted">{t("pilot.lead")}</p>
      </div>
      {error && <Alert tone="danger" role="alert">{error}</Alert>}

      {req?.status === "new" && (
        <Alert tone="info" icon="hourglass" role="status" title={t("pilot.waitingTitle")}>{t("pilot.waiting", { name: lawyerName })}</Alert>
      )}

      {req?.status === "accepted" && (
        <div className="card space-y-3">
          <p className="flex items-start gap-2 text-sm"><Icon name="checkCircle" size={20} className="shrink-0 text-brand" />{t("pilot.accepted", { name: lawyerName })}</p>
          {!bill && (s.payment_available ? (
            <Button className="min-h-12 w-full" disabled={busy} icon="coin" onClick={() => run(`/v1/cases/${caseId}/lawyer-payment`)}>
              {t("pilot.pay", { price: money(req.price ?? 0, s.currency) })}
            </Button>
          ) : <p className="rounded-xl bg-sand p-3 text-sm">{t("pilot.payLater")}</p>)}
          {bill && (
            <div className="space-y-3">
              <p className="text-2xl font-semibold tabular-nums">{money(bill.amount, bill.currency)}</p>
              {bill.company_name && <p className="text-sm">{t("pilot.payTo", { name: bill.company_name })}</p>}
              {bill.kaspi_pay_link && <Button href={bill.kaspi_pay_link} variant="secondary" className="w-full" icon="external">{t("pilot.payLink")}</Button>}
              {bill.company_account && (
                <div className="space-y-1">
                  <p className="text-xs text-muted">{t("pilot.payAccount")}</p>
                  <p className="whitespace-pre-line rounded-xl bg-sand p-3 text-sm" dir="auto">{bill.company_account}</p>
                </div>
              )}
              <div className="space-y-1">
                <p className="text-xs text-muted">{t("pilot.payCode")}</p>
                <p className="font-mono text-lg" dir="ltr">{bill.code}</p>
              </div>
              <p className="text-xs text-muted">{t("pilot.companyNote")}</p>
              {bill.status === "not_found" && <Alert tone="warning" role="status">{t("pilot.notFound", { code: bill.code })}</Alert>}
              {bill.status === "awaiting_confirmation" ? (
                <Alert tone="info" icon="hourglass" role="status">{t("pilot.checking")}</Alert>
              ) : (
                <Button className="min-h-12 w-full" disabled={busy} icon="check" onClick={() => run(`/v1/cases/${caseId}/lawyer-payment/claim`)}>
                  {t("pilot.paidBtn")}
                </Button>
              )}
            </div>
          )}
        </div>
      )}

      {(req?.status === "paid" || req?.status === "closed") && (
        <Alert tone="info" icon="checkCircle" role="status">{t("pilot.paid", { name: lawyerName })}</Alert>
      )}

      {!req && (
        <>
          {s.last?.status === "declined" && (
            <Alert tone="warning" role="status">{t("pilot.declined", { name: s.last.lawyer?.name ?? "" })}</Alert>
          )}
          {s.lawyers.length === 0 && <ComingSoon caseId={caseId} />}
          <ul className="space-y-3">
            {s.lawyers.map((l) => (
              <LawyerCard key={l.id} l={{ id: String(l.id), name: l.name, kind: l.kind_label, organization: l.organization, city: l.city,
                specializations: l.specializations.map((x) => x.label), price: l.price, priceNote: l.price_note,
                response: t("choose.workday"), rating: null }} action={
                open === l.id ? (
                  <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); send(l.id); }}>
                    <p className="text-sm text-muted">{t("pilot.contactsHint")}</p>
                    <label className="block space-y-1 text-sm">
                      <span>{t("request.name")}</span>
                      <input className="input" autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} required />
                    </label>
                    <label className="block space-y-1 text-sm">
                      <span>{t("request.phone")}</span>
                      <input className="input" type="tel" inputMode="tel" autoComplete="tel" dir="ltr" value={phone}
                        onChange={(e) => setPhone(e.target.value)} placeholder="+7 7__ ___ __ __" required />
                    </label>
                    <label className="flex items-start gap-2 text-sm">
                      <input type="checkbox" className="mt-1 h-5 w-5 shrink-0" checked={consent} onChange={(e) => setConsent(e.target.checked)} required />
                      <span>{t("pilot.consent")}</span>
                    </label>
                    <div className="flex gap-2">
                      <Button type="submit" className="min-h-12 flex-1" disabled={busy || !consent} icon="send">{t("pilot.send")}</Button>
                      <Button type="button" variant="secondary" className="min-h-12" onClick={() => setOpen(null)}>{t("pilot.cancel")}</Button>
                    </div>
                  </form>
                ) : (
                  <Button className="min-h-12 w-full" icon="check" onClick={() => { setOpen(l.id); setError(null); }}>{t("choose.choose")}</Button>
                )} />
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

/** No pilot lawyer yet: say so plainly and take a request — the team calls back when one is connected. */
function ComingSoon({ caseId }: { caseId: string }) {
  const t = useT();
  const [contact, setContact] = useState("");
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function send(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      await api("/v1/waitlist", { method: "POST", body: JSON.stringify({ country: "KZ", contact: contact.trim(), problem: `Юрист по делу ${caseId}` }) });
      setSent(true);
    } catch (err) { setError(errorText(err)); } finally { setBusy(false); }
  }
  return (
    <div className="card space-y-3">
      <p className="flex items-center gap-2 font-semibold"><Icon name="hourglass" size={20} className="text-brand" />{t("choose.soonTitle")}</p>
      <p className="text-sm text-muted">{t("choose.soonText")}</p>
      {sent ? <Alert tone="info" icon="checkCircle" role="status">{t("choose.soonSent")}</Alert> : (
        <form className="space-y-2" onSubmit={send}>
          <label className="block space-y-1 text-sm">
            <span>{t("choose.soonContact")}</span>
            <input className="input" value={contact} onChange={(e) => setContact(e.target.value)} placeholder="+7 701 123 45 67" required minLength={5} autoComplete="tel" />
          </label>
          <Button type="submit" className="min-h-12 w-full" icon="send" disabled={busy}>{t("choose.soonButton")}</Button>
        </form>
      )}
      {error && <Alert tone="danger" role="alert">{error}</Alert>}
    </div>
  );
}
