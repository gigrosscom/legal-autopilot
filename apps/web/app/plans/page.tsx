"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Alert, Button, Icon } from "@/components/ui";
import { api, ApiError, errorText, type PlansView } from "@/lib/api";
import { useLang, useT } from "@/lib/i18n";

const PLANS = ["biz", "bizpro"] as const;

function money(amount: number, currency: string | null): string {
  return `${amount.toLocaleString("ru-RU").replace(/ /g, " ")} ${currency === "KZT" ? "₸" : currency ?? ""}`.trim();
}

function CopyValue({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  const t = useT();
  const [copied, setCopied] = useState(false);
  return (
    <div className="flex items-center justify-between gap-3 rounded-xl bg-sand px-3 py-2">
      <div className="min-w-0">
        <p className="text-xs text-muted">{label}</p>
        <p dir="ltr" className={`break-all text-base font-semibold ${mono ? "font-mono tracking-wider" : ""}`}>{value}</p>
      </div>
      <button type="button" className="btn-ghost shrink-0 text-sm"
        onClick={async () => { try { await navigator.clipboard.writeText(value); setCopied(true); setTimeout(() => setCopied(false), 2000); } catch {} }}>
        {copied ? t("payment.copied") : t("payment.copy")}
      </button>
    </div>
  );
}

/** «Бизнес» and «Бизнес Про»: choose a plan, transfer by Kaspi with the payment code, press "I have paid";
 *  the clients desk confirms the transfer and the 30-day period starts. */
export default function PlansPage() {
  const t = useT();
  const { lang } = useLang();
  const [view, setView] = useState<PlansView | null>(null);
  const [chosen, setChosen] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => api<PlansView>("/v1/plans").then(setView).catch((e) => setError(errorText(e))), []);
  useEffect(() => {
    load();
    const p = new URLSearchParams(window.location.search).get("plan");
    if (p && (PLANS as readonly string[]).includes(p)) setChosen(p);
  }, [load]);

  async function post(path: string) {
    setBusy(true); setError(null);
    try { setView(await api<PlansView>(path, { method: "POST" })); }
    catch (e) { setError(e instanceof ApiError && e.code === "contact_required" ? t("plans.signIn") : errorText(e)); }
    finally { setBusy(false); }
  }

  const name = (k: string) => t(`home.price.${k}T`);
  const inv = view?.invoice;
  const date = (iso: string) => new Date(iso).toLocaleDateString(lang === "kk" ? "kk-KZ" : lang);

  return (
    <div className="mx-auto max-w-3xl space-y-8">
      <div className="space-y-2">
        <h1 className="text-3xl font-semibold tracking-tight">{t("plans.title")}</h1>
        <p className="text-muted">{t("plans.lead")}</p>
      </div>
      {error && <Alert tone="danger" role="alert">{error}</Alert>}
      {view?.subscription && (
        <Alert tone="info" icon="checkCircle" role="status">
          {t("plans.active", { plan: name(view.subscription.plan), date: date(view.subscription.ends_at),
            n: view.subscription.left })}
        </Alert>
      )}

      {view && (
        <ul className="grid gap-4 md:grid-cols-2">
          {PLANS.map((k) => {
            const p = view.plans[k];
            if (!p) return null;
            return (
              <li key={k} className={`card flex flex-col gap-3 ${chosen === k ? "ring-2 ring-brand/40" : ""}`}>
                <Icon name={k === "biz" ? "briefcase" : "building"} size={26} className="text-ink" />
                <h2 className="text-[21px] font-semibold tracking-[-0.015em]">{name(k)}</h2>
                <p className="text-[32px] leading-tight font-semibold tracking-[-0.02em]">
                  {money(p.price, view.currency)} <span className="text-[17px] font-normal tracking-normal text-muted">{t("home.price.perMonth")}</span>
                </p>
                <p className="flex-1 text-[17px] leading-[1.47] text-muted">{t("plans.documents", { n: p.documents, days: p.days })}</p>
                <Button className="min-h-12 w-full" disabled={busy || !view.available || !!inv}
                  variant={chosen === k ? undefined : "secondary"}
                  onClick={() => { setChosen(k); post(`/v1/plans/${k}/invoice`); }}>{t("plans.buy")}</Button>
              </li>
            );
          })}
        </ul>
      )}

      {view && !view.available && (
        <p className="flex items-center gap-2 text-sm"><Icon name="alert" size={18} className="text-warning" />{t("payment.unavailable")}</p>
      )}
      {view && !view.signed_in && (
        <Alert tone="info" role="status" actions={<Button href="/account" variant="secondary">{t("plans.signInCta")}</Button>}>
          {t("plans.signIn")}
        </Alert>
      )}

      {inv && (
        <section className="card space-y-3 border-brand/40" aria-labelledby="pay-title">
          <h2 id="pay-title" className="flex items-center gap-2 text-lg font-semibold">
            <Icon name="coin" className="text-brand" />{t("plans.payTitle", { plan: name(inv.plan ?? "") })}
          </h2>
          {inv.status === "awaiting_confirmation" && <Alert tone="info" icon="hourglass" role="status">{t("payment.waiting")}</Alert>}
          {inv.status === "not_found" && <Alert tone="warning" role="status">{t("payment.notFound")}</Alert>}
          <p className="text-2xl font-semibold tabular-nums">{money(inv.amount, inv.currency)}</p>
          <div className="space-y-2">
            {inv.recipient_name && <CopyValue label={t("payment.recipient")} value={inv.recipient_name} />}
            {inv.kaspi_phone && <CopyValue label={t("payment.kaspi")} value={inv.kaspi_phone} />}
            <CopyValue label={t("payment.code")} value={inv.code} mono />
          </div>
          <p className="text-sm">{t("payment.steps")}</p>
          {inv.status === "awaiting_confirmation" ? (
            <Button className="min-h-12 w-full" variant="secondary" disabled={busy} icon="hourglass" onClick={() => load()}>{t("payment.refresh")}</Button>
          ) : (
            <Button className="min-h-12 w-full" disabled={busy} icon="check" onClick={() => post("/v1/plans/invoice/claim")}>{t("payment.paid")}</Button>
          )}
        </section>
      )}

      <p className="text-sm text-muted">
        {t("plans.forPeople")} <Link href="/start" className="link">{t("plans.forPeopleCta")}</Link>
      </p>
    </div>
  );
}
