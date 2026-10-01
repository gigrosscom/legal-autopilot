"use client";

import { useState } from "react";
import { PaymentWays, type WayBody } from "@/components/PaymentWays";
import { Alert, Badge, Button, Icon } from "@/components/ui";
import type { Tone } from "@/components/ui/Badge";
import {
  ApiError,
  api,
  errorText,
  fetchFile,
  saveBlob,
  type CaseAction,
  type CaseView,
  type CourierDelivery as Delivery,
  type CourierForm,
  type CourierState,
  type CourierStatus,
  type Payment,
} from "@/lib/api";
import { useLang, useT } from "@/lib/i18n";

type Out = { courier: CourierState | null; case: CaseView };

const STEPS: CourierStatus[] = ["ordered", "picked_up", "in_transit", "delivered", "returned"];
const TONE: Record<CourierStatus, Tone> = {
  awaiting_payment: "warning", paid: "info", ordered: "info", picked_up: "info", in_transit: "info",
  delivered: "brand", refused: "danger", returned: "brand", cancelled: "neutral",
};

function money(amount: number, currency: string | null): string {
  return `${amount.toLocaleString("ru-RU").replace(/ /g, " ")} ${currency === "KZT" ? "₸" : currency ?? ""}`.trim();
}

/** «Доставить курьером» (pilot «Курьер», owner 01.10.2026): on a paid document the client orders the courier — the
 *  pickup address and a time window, the price, then the same payment as the document's. Our system orders the
 *  courier; the card follows the order: picked up → on the way → delivered against a signature → second copy back. */
export function CourierDelivery({ caseId, a, onCase }: { caseId: string; a: CaseAction; onCase?: (c: CaseView) => void }) {
  const t = useT();
  const [state, setState] = useState<CourierState | null | undefined>(undefined);
  const [form, setForm] = useState<CourierForm | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const courier = state === undefined ? a.courier : state;
  if (!courier || (!courier.available && !courier.delivery)) return null;
  const d = courier.delivery;
  const live = d && !["cancelled", "refused"].includes(d.status);

  const explain = (e: unknown) => {
    if (e instanceof ApiError && e.code) {
      const key = `courier.errors.${e.code}`;
      const text = t(key);
      if (text !== key) return text;
    }
    return errorText(e);
  };
  const done = (out: Out) => { setState(out.courier); onCase?.(out.case); };

  async function open() {
    setBusy(true); setError(null);
    try { setForm(await api<CourierForm>(`/v1/cases/${caseId}/actions/${a.id}/courier`)); }
    catch (e) { setError(explain(e)); } finally { setBusy(false); }
  }

  if (live && d) return <DeliveryCard caseId={caseId} d={d} onOut={done} explain={explain} />;
  return (
    <section className="space-y-2 rounded-2xl border border-line p-3" aria-label={t("courier.title")}>
      {d?.status === "refused" && <Alert tone="warning" role="status">{t("courier.refusedNote")}</Alert>}
      {!form ? (
        <>
          <div className="flex items-start gap-2">
            <Icon name="truck" size={20} className="mt-0.5 text-brand" />
            <div className="min-w-0">
              <p className="font-semibold">{t("courier.title")}</p>
              <p className="text-xs text-muted">{t("courier.lead")}</p>
            </div>
          </div>
          {courier.available && (
            <Button className="min-h-12 w-full" variant="secondary" icon={busy ? "spinner" : "truck"} disabled={busy} onClick={open}>
              {t("courier.order", { price: money(courier.price ?? 0, courier.currency) })}
            </Button>
          )}
        </>
      ) : (
        <OrderForm caseId={caseId} a={a} form={form} onCancel={() => setForm(null)} explain={explain}
          onDone={(out) => { setForm(null); done(out); }} />
      )}
      {error && <p role="alert" className="text-xs text-danger">{error}</p>}
    </section>
  );
}

function OrderForm({ caseId, a, form, onCancel, onDone, explain }: {
  caseId: string; a: CaseAction; form: CourierForm; onCancel: () => void; onDone: (out: Out) => void;
  explain: (e: unknown) => string;
}) {
  const t = useT();
  const def = form.defaults;
  const [v, setV] = useState({
    city: form.cities?.[0]?.id ?? "", date: form.min_date ?? "", window: form.windows?.[0] ?? "",
    pickup_address: "", contact_name: def?.contact_name ?? "", contact_phone: def?.contact_phone ?? "",
    recipient_name: def?.recipient_name ?? "", recipient_address: def?.recipient_address ?? "",
    recipient_phone: def?.recipient_phone ?? "", comment: "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const set = (k: keyof typeof v) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setV((x) => ({ ...x, [k]: e.target.value }));
  const id = (k: string) => `courier-${a.id}-${k}`;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      onDone(await api<Out>(`/v1/cases/${caseId}/actions/${a.id}/courier`, {
        method: "POST", body: JSON.stringify({ ...v, recipient_phone: v.recipient_phone || null, comment: v.comment || null }),
      }));
    } catch (err) { setError(explain(err)); } finally { setBusy(false); }
  }

  const field = (k: keyof typeof v, label: string, extra: React.InputHTMLAttributes<HTMLInputElement> = {}) => (
    <div className="space-y-1">
      <label htmlFor={id(k)} className="block text-sm">{label}</label>
      <input id={id(k)} className="input min-h-12" value={v[k]} onChange={set(k)} {...extra} />
    </div>
  );

  return (
    <form className="space-y-3" onSubmit={submit}>
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="font-semibold">{t("courier.title")}</p>
          {form.note && <p className="text-xs text-muted">{form.note}</p>}
        </div>
        <button type="button" className="p-1 text-muted" aria-label={t("app.cancel")} onClick={onCancel}><Icon name="x" size={18} /></button>
      </div>

      <p className="text-sm font-semibold">1. {t("courier.pickup")}</p>
      {(form.cities?.length ?? 0) > 1 ? (
        <div className="space-y-1">
          <label htmlFor={id("city")} className="block text-sm">{t("courier.city")}</label>
          <select id={id("city")} className="input min-h-12" value={v.city} onChange={set("city")}>
            {form.cities!.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </div>
      ) : form.cities?.[0] && <p className="text-sm text-muted">{t("courier.cityOnly", { city: form.cities[0].name })}</p>}
      {field("pickup_address", t("courier.pickupAddress"), { required: true, minLength: 5, maxLength: 500, autoComplete: "street-address" })}
      <div className="grid gap-2 sm:grid-cols-2">
        {field("date", t("courier.date"), { type: "date", required: true, min: form.min_date, max: form.max_date })}
        <div className="space-y-1">
          <span className="block text-sm">{t("courier.window")}</span>
          <div role="radiogroup" aria-label={t("courier.window")} className="flex flex-wrap gap-2">
            {(form.windows ?? []).map((w) => (
              <button key={w} type="button" role="radio" aria-checked={v.window === w} onClick={() => setV((x) => ({ ...x, window: w }))}
                className={`min-h-12 rounded-xl border px-3 text-sm tabular-nums ${v.window === w ? "border-brand bg-brand-50 font-semibold text-brand" : "border-line bg-surface"}`}>
                {w.replace("-", "–")}
              </button>
            ))}
          </div>
        </div>
      </div>
      {field("contact_name", t("courier.contactName"), { required: true, minLength: 2, maxLength: 200, autoComplete: "name" })}
      {field("contact_phone", t("courier.contactPhone"), { required: true, inputMode: "tel", autoComplete: "tel", dir: "ltr", placeholder: "+7 7__ ___ __ __" })}

      <p className="text-sm font-semibold">2. {t("courier.recipient")}</p>
      {field("recipient_name", t("courier.recipientName"), { required: true, minLength: 2, maxLength: 500 })}
      {field("recipient_address", t("courier.recipientAddress"), { required: true, minLength: 5, maxLength: 500 })}
      {field("recipient_phone", form.recipient_phone_required ? t("courier.recipientPhone") : t("courier.recipientPhoneOptional"),
        { required: !!form.recipient_phone_required, inputMode: "tel", dir: "ltr" })}
      {field("comment", t("courier.comment"), { maxLength: 500 })}

      {form.print_hint && <Alert tone="info" icon="printer" role="note">{form.print_hint}</Alert>}
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-sm">{t("courier.price")}</span>
        <span className="text-xl font-semibold tabular-nums">{money(form.price ?? 0, form.currency)}</span>
      </div>
      <Button type="submit" className="min-h-12 w-full" icon={busy ? "spinner" : "truck"} disabled={busy || !v.window}>
        {t("courier.submit")}
      </Button>
      {error && <p role="alert" className="text-xs text-danger">{error}</p>}
    </form>
  );
}

function DeliveryCard({ caseId, d, onOut, explain }: {
  caseId: string; d: Delivery; onOut: (out: Out) => void; explain: (e: unknown) => string;
}) {
  const t = useT();
  const { lang } = useLang();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const at = (iso: string | null) => iso ? new Date(iso).toLocaleString(lang === "en" ? "en-GB" : "ru-RU",
    { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "";
  const reached: Partial<Record<CourierStatus, string | null>> = {
    ordered: d.ordered_at, picked_up: d.picked_up_at,
    in_transit: d.events.find((e) => e.status === "in_transit")?.at ?? null,
    delivered: d.delivered_at, returned: d.returned_at,
  };
  const rank = STEPS.indexOf(d.status);
  const pickup = `${new Date(`${d.pickup_date}T00:00:00`).toLocaleDateString(lang === "en" ? "en-GB" : "ru-RU")}, ${d.pickup_from}–${d.pickup_to}`;

  async function run(fn: () => Promise<Out | void>) {
    setBusy(true); setError(null);
    try { const out = await fn(); if (out) onOut(out); } catch (e) { setError(explain(e)); } finally { setBusy(false); }
  }
  const claim = () => api<Out>(`/v1/cases/${caseId}/courier/${d.id}/claim`, { method: "POST", body: "{}" });
  const onWay = (body: WayBody, then?: "claim" | "bill") => run(async () => {
    const inv = d.invoice;
    if (!inv) return;
    const out = await api<{ case: CaseView }>(`/v1/invoices/${inv.id}/way`, { method: "POST", body: JSON.stringify(body) });
    if (then === "bill") {
      const blob = await fetchFile(`/v1/invoices/${inv.id}/bill?format=pdf`);
      saveBlob(blob, `schet-${inv.id}.${blob.type.includes("pdf") ? "pdf" : "docx"}`);
    }
    if (then === "claim") return claim();
    const act = out.case.actions.find((x) => x.courier?.delivery?.id === d.id);
    return { courier: act?.courier ?? null, case: out.case };
  });

  const inv = d.invoice;
  const waiting = inv?.status === "awaiting_confirmation";
  return (
    <section className="space-y-3 rounded-2xl border border-line p-3" aria-label={t("courier.title")}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="flex items-center gap-2 font-semibold"><Icon name="truck" size={20} className="text-brand" />{t("courier.title")}</p>
        <Badge tone={TONE[d.status]}>{t(`courier.status.${d.status}`)}</Badge>
      </div>
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
        <dt className="text-muted">{t("courier.pickup")}</dt><dd className="break-words">{pickup} · {d.pickup_address}</dd>
        <dt className="text-muted">{t("courier.recipient")}</dt><dd className="break-words">{d.recipient_name}, {d.recipient_address}</dd>
        {d.tracking && (<><dt className="text-muted">{t("courier.tracking")}</dt><dd dir="ltr" className="font-mono">{d.tracking} · {d.provider_label}</dd></>)}
        {d.signer_name && (<><dt className="text-muted">{t("courier.signer")}</dt><dd>{d.signer_name}</dd></>)}
      </dl>

      {d.status === "awaiting_payment" && inv ? (
        <div className="space-y-3 rounded-2xl bg-brand-50 p-3">
          <div className="flex items-baseline justify-between gap-3">
            <span className="text-sm">{t("courier.service")}</span>
            <span className="text-xl font-semibold tabular-nums">{money(inv.amount, inv.currency)}</span>
          </div>
          {waiting && <Alert tone="info" icon="hourglass" role="status">{t("payment.waiting")}</Alert>}
          {inv.status === "not_found" && <Alert tone="warning" role="status">{t("payment.notFound")}</Alert>}
          {inv.ways?.length ? (
            <PaymentWays pay={{ ...inv, invoice_id: inv.id, method: "", available: true, options: [], case_paid: false,
              credits: 0, bonus: 0, subscription: null, purpose: null } as Payment} busy={busy} amount={String(inv.amount)}
              onWay={onWay} copy={(label, value, mono) => <Row key={label} label={label} value={value} mono={mono} />}
              transfer={<Transfer inv={inv} />} />
          ) : (
            <>
              <Transfer inv={inv} />
              {!waiting && <Button className="min-h-12 w-full" disabled={busy} icon="check" onClick={() => run(claim)}>{t("payment.paid")}</Button>}
            </>
          )}
          {!waiting && (
            <button type="button" className="text-xs text-muted underline" disabled={busy}
              onClick={() => run(() => api<Out>(`/v1/cases/${caseId}/courier/${d.id}/cancel`, { method: "POST", body: "{}" }))}>
              {t("courier.cancel")}
            </button>
          )}
        </div>
      ) : (
        <ol className="space-y-1.5">
          {d.status === "paid" && (
            <li className="flex items-center gap-2 text-sm"><Icon name="hourglass" size={16} className="text-brand" />{t("courier.status.paid")}</li>
          )}
          {STEPS.map((s, i) => (
            <li key={s} className={`flex items-center gap-2 text-sm ${i <= rank ? "" : "text-muted"}`}>
              <Icon name={i <= rank ? "checkCircle" : "clock"} size={16} className={i <= rank ? "text-brand" : ""} />
              <span className="min-w-0 flex-1">{t(`courier.steps.${s}`)}</span>
              {i <= rank && reached[s] && <span className="text-xs tabular-nums text-muted">{at(reached[s] ?? null)}</span>}
            </li>
          ))}
        </ol>
      )}
      {d.print_hint && ["paid", "ordered"].includes(d.status) && <p className="text-xs text-muted">{d.print_hint}</p>}
      {d.status === "delivered" && <p className="text-xs text-muted">{t("courier.deliveredNote")}</p>}
      {error && <p role="alert" className="text-xs text-danger">{error}</p>}
    </section>
  );
}

function Transfer({ inv }: { inv: NonNullable<Delivery["invoice"]> }) {
  const t = useT();
  return (
    <div className="space-y-2">
      {inv.recipient_name && <Row label={t("payment.recipient")} value={inv.recipient_name} />}
      {inv.kaspi_phone && <Row label={t("payment.kaspi")} value={inv.kaspi_phone} />}
      {inv.code && <Row label={t("payment.code")} value={inv.code} mono />}
      <p className="text-sm">{t("payment.steps")}</p>
    </div>
  );
}

function Row({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  const t = useT();
  const [copied, setCopied] = useState(false);
  return (
    <div className="flex items-center justify-between gap-3 rounded-xl bg-surface px-3 py-2">
      <div className="min-w-0">
        <p className="text-xs text-muted">{label}</p>
        <p dir="ltr" className={`break-all text-base font-semibold ${mono ? "font-mono tracking-wider" : ""}`}>{value}</p>
      </div>
      <button type="button" className="btn-ghost shrink-0 text-sm"
        onClick={async () => { try { await navigator.clipboard.writeText(value); setCopied(true); setTimeout(() => setCopied(false), 2000); } catch { /* no clipboard */ } }}>
        {copied ? t("payment.copied") : t("payment.copy")}
      </button>
    </div>
  );
}
