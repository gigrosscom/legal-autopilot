"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { PaymentWays, type WayBody } from "@/components/PaymentWays";
import { Alert, Button, Icon } from "@/components/ui";
import { ApiError, api, downloadFile, errorText, fetchFile, saveBlob } from "@/lib/api";
import {
  COURIER_STEPS, dateText, reachedStep, type CourierOrder, type CourierRequest, type CourierState, type CourierStep,
} from "@/lib/courier";
import { useLang, useT } from "@/lib/i18n";

function money(amount: number, currency: string | null | undefined): string {
  return `${amount.toLocaleString("ru-RU").replace(/ /g, " ")} ${currency === "KZT" ? "₸" : currency ?? ""}`.trim();
}

/** «Доставить ответчику курьером в руки» (pilot, owner 01.10): after the paid document — order in two steps, pay on
 *  the same Kaspi screen as the document, then follow the delivery to the answer. Hidden when the server has no
 *  courier for this case (another city, a state body, the pilot is full) or does not know the endpoint yet. */
export function CourierCard({ caseId }: { caseId: string }) {
  const t = useT();
  const [s, setS] = useState<CourierState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState(false);

  const load = useCallback(() => api<CourierState>(`/v1/cases/${caseId}/courier`)
    .then((v) => { setS(v); setError(null); })
    .catch(() => setS(null)), [caseId]);
  useEffect(() => { load(); }, [load]);

  // the payment is being checked or the courier is on the way: look again now and then
  const order = s?.order ?? null;
  const moving = !!order && !["answered", "cancelled"].includes(order.status);
  useEffect(() => {
    if (!moving) return;
    const timer = setInterval(() => { load(); }, order?.status === "awaiting_payment" ? 5000 : 60000);
    return () => clearInterval(timer);
  }, [moving, order?.status, load]);

  async function run<T>(fn: () => Promise<T>): Promise<T | null> {
    setBusy(true);
    setError(null);
    try {
      return await fn();
    } catch (e) {
      const code = e instanceof ApiError ? e.code : null;
      setError(code && ["consent_required", "slot_unavailable", "courier_unavailable"].includes(code) ? t(`courier.error.${code}`) : errorText(e));
      return null;
    } finally { setBusy(false); }
  }

  async function order_(body: CourierRequest) {
    const out = await run(() => api<{ order: CourierOrder }>(`/v1/cases/${caseId}/courier`, { method: "POST", body: JSON.stringify(body) }));
    if (out) { setForm(false); setS((v) => (v ? { ...v, order: out.order } : v)); }
  }

  async function way(body: WayBody, then?: "claim" | "bill") {
    const invoice = order?.payment?.invoice_id;
    if (!invoice) return;
    await run(async () => {
      await api(`/v1/invoices/${invoice}/way`, { method: "POST", body: JSON.stringify(body) });
      if (then === "claim") await api(`/v1/cases/${caseId}/courier/claim`, { method: "POST", body: "{}" });
      if (then === "bill") {
        const blob = await fetchFile(`/v1/invoices/${invoice}/bill?format=pdf`);
        saveBlob(blob, `schet-${invoice}.${blob.type.includes("pdf") ? "pdf" : "docx"}`);
      }
      await load();
    });
  }

  async function answer(files: File[]) {
    const body = new FormData();
    files.forEach((f) => body.append("files", f));
    const out = await run(() => api<{ order: CourierOrder }>(`/v1/cases/${caseId}/courier/answer`, { method: "POST", body }));
    if (out) setS((v) => (v ? { ...v, order: out.order } : v));
  }

  if (!s || (!s.available && !order)) return null;

  return (
    <section aria-labelledby="courier-title" className="space-y-3 rounded-2xl border border-line bg-surface p-4">
      <h2 id="courier-title" className="flex items-center gap-2 text-base font-semibold">
        <Icon name="truck" size={22} className="shrink-0 text-brand" />
        <span className="flex-1">{order ? t("courier.statusTitle") : t("courier.title")}</span>
        {!order && <span className="tabular-nums">{money(s.price, s.currency)}</span>}
      </h2>
      {error && <Alert tone="danger" role="alert">{error}</Alert>}

      {!order && !form && (
        <>
          <p className="text-sm text-muted">{t("courier.lead")}</p>
          {s.city && <p className="flex items-center gap-1.5 text-xs text-muted"><Icon name="map" size={16} />{t("courier.city", { city: s.city })}</p>}
          <Button className="min-h-12 w-full" icon="truck" onClick={() => setForm(true)}>{t("courier.order", { price: money(s.price, s.currency) })}</Button>
        </>
      )}

      {!order && form && <OrderForm s={s} busy={busy} onCancel={() => setForm(false)} onSubmit={order_} />}

      {order?.status === "awaiting_payment" && order.payment && (
        <CourierPayment order={order} busy={busy} onWay={way}
          onClaim={() => run(async () => { await api(`/v1/cases/${caseId}/courier/claim`, { method: "POST", body: "{}" }); await load(); })} />
      )}

      {order && order.status !== "awaiting_payment" && <Timeline order={order} busy={busy} onAnswer={answer} />}
    </section>
  );
}

function OrderForm({ s, busy, onCancel, onSubmit }: {
  s: CourierState; busy: boolean; onCancel: () => void; onSubmit: (body: CourierRequest) => void;
}) {
  const t = useT();
  const { lang } = useLang();
  const [step, setStep] = useState<1 | 2>(1);
  const [address, setAddress] = useState(s.pickup?.address ?? "");
  const [date, setDate] = useState(s.slots[0]?.date ?? "");
  const [window_, setWindow] = useState("");
  const [phone, setPhone] = useState(s.pickup?.phone ?? "");
  const [note, setNote] = useState("");
  const [name, setName] = useState(s.respondent?.name ?? "");
  const [where, setWhere] = useState(s.respondent?.address ?? "");
  const [consent, setConsent] = useState(false);
  const top = useRef<HTMLDivElement>(null);
  const windows = s.slots.find((x) => x.date === date)?.windows ?? [];
  const day = (iso: string) => dateText(iso, lang, { weekday: true });

  useEffect(() => { top.current?.scrollIntoView({ block: "nearest" }); }, [step]);
  useEffect(() => { if (!windows.some((w) => w.id === window_)) setWindow(windows[0]?.id ?? ""); }, [date]);  // eslint-disable-line react-hooks/exhaustive-deps

  const chip = (on: boolean) => `min-h-11 rounded-xl border px-3 text-sm ${on ? "border-brand bg-brand-50 font-semibold text-brand" : "border-line bg-surface"}`;

  return (
    <div ref={top} className="space-y-4">
      <p className="text-xs font-semibold text-muted">{t("courier.stepOf", { n: step })}</p>
      {step === 1 ? (
        <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); setStep(2); }}>
          <h3 className="font-semibold">{t("courier.step1")}</h3>
          <label className="block space-y-1 text-sm">
            <span>{t("courier.pickupAddress")}</span>
            <input className="input" autoComplete="street-address" value={address} onChange={(e) => setAddress(e.target.value)}
              placeholder={t("courier.pickupHint")} required minLength={5} />
          </label>
          <fieldset className="space-y-2">
            <legend className="text-sm">{t("courier.date")}</legend>
            <div role="radiogroup" aria-label={t("courier.date")} className="flex flex-wrap gap-2">
              {s.slots.map((x) => (
                <button key={x.date} type="button" role="radio" aria-checked={date === x.date} onClick={() => setDate(x.date)} className={chip(date === x.date)}>
                  {day(x.date)}
                </button>
              ))}
            </div>
          </fieldset>
          <fieldset className="space-y-2">
            <legend className="text-sm">{t("courier.window")}</legend>
            <div role="radiogroup" aria-label={t("courier.window")} className="grid grid-cols-3 gap-2">
              {windows.map((w) => (
                <button key={w.id} type="button" role="radio" aria-checked={window_ === w.id} onClick={() => setWindow(w.id)}
                  className={`${chip(window_ === w.id)} whitespace-nowrap px-1 text-[13px] tabular-nums`} dir="ltr">{w.label}</button>
              ))}
            </div>
          </fieldset>
          <label className="block space-y-1 text-sm">
            <span>{t("courier.phone")}</span>
            <input className="input" type="tel" inputMode="tel" autoComplete="tel" dir="ltr" value={phone}
              onChange={(e) => setPhone(e.target.value)} placeholder="+7 7__ ___ __ __" required minLength={10} />
          </label>
          <label className="block space-y-1 text-sm">
            <span>{t("courier.note")}</span>
            <input className="input" value={note} onChange={(e) => setNote(e.target.value)} placeholder={t("courier.notePlaceholder")} />
          </label>
          <div className="flex gap-2">
            <Button type="submit" className="min-h-12 flex-1" iconEnd="arrowRight" disabled={!date || !window_}>{t("courier.next")}</Button>
            <Button type="button" variant="secondary" className="min-h-12" onClick={onCancel}>{t("courier.cancel")}</Button>
          </div>
        </form>
      ) : (
        <form className="space-y-4" onSubmit={(e) => {
          e.preventDefault();
          onSubmit({ pickup_address: address.trim(), pickup_date: date, pickup_window: window_, phone: phone.trim(),
            respondent_name: name.trim(), respondent_address: where.trim(), note: note.trim(), consent: true });
        }}>
          <h3 className="font-semibold">{t("courier.step2")}</h3>
          <p className="text-xs text-muted">{t("courier.fromDocument")}</p>
          <label className="block space-y-1 text-sm">
            <span>{t("courier.respondentName")}</span>
            <input className="input" value={name} onChange={(e) => setName(e.target.value)} required minLength={2} />
          </label>
          <label className="block space-y-1 text-sm">
            <span>{t("courier.respondentAddress")}</span>
            <textarea className="input min-h-20" value={where} onChange={(e) => setWhere(e.target.value)} required minLength={5} />
          </label>

          <div className="space-y-2 rounded-xl bg-sand p-3 text-sm">
            <p className="flex items-center gap-2 font-semibold"><Icon name="printer" size={18} className="text-brand" />{t("courier.prepareTitle")}</p>
            <ol className="list-decimal space-y-1 ps-5">
              <li>{t("courier.prepare1")}</li>
              <li>{t("courier.prepare2")}</li>
              <li>{t("courier.prepare3")}</li>
            </ol>
            <p className="text-xs text-muted">{t("courier.esignNote")}</p>
          </div>

          <p className="text-xs text-muted">{t("courier.terms")}</p>
          <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" className="mt-1 h-5 w-5 shrink-0" checked={consent} onChange={(e) => setConsent(e.target.checked)} required />
            <span>{t("courier.consent")}</span>
          </label>
          <div className="flex gap-2">
            <Button type="submit" className="min-h-12 flex-1" icon="coin" disabled={busy || !consent}>
              {t("courier.toPay", { price: money(s.price, s.currency) })}
            </Button>
            <Button type="button" variant="secondary" className="min-h-12" onClick={() => setStep(1)}>{t("courier.back")}</Button>
          </div>
        </form>
      )}
    </div>
  );
}

/** The same Kaspi screen as the document's: the amount, the ways the server switched on, «Оплатил(а)». */
function CourierPayment({ order, busy, onWay, onClaim }: {
  order: CourierOrder; busy: boolean; onWay: (body: WayBody, then?: "claim" | "bill") => void; onClaim: () => void;
}) {
  const t = useT();
  const { lang } = useLang();
  const pay = order.payment!;
  const waiting = pay.status === "awaiting_confirmation";
  const day = dateText(order.pickup_date, lang, { weekday: true });
  const transfer = (
    <>
      <div className="space-y-2">
        {pay.recipient_name && <CopyRow label={t("payment.recipient")} value={pay.recipient_name} />}
        {pay.kaspi_phone && <CopyRow label={t("payment.kaspi")} value={pay.kaspi_phone} />}
        {pay.code && <CopyRow label={t("payment.code")} value={pay.code} mono />}
      </div>
      <p className="text-sm">{t("payment.steps")}</p>
    </>
  );
  return (
    <div className="space-y-3">
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 text-sm">
        <dt className="text-muted">{t("courier.service")}</dt>
        <dd className="text-end font-semibold">{t("courier.serviceName")}</dd>
        <dt className="text-muted">{t("courier.to")}</dt>
        <dd className="text-end">{order.respondent_name}</dd>
        <dt className="text-muted">{t("courier.pickup")}</dt>
        <dd className="text-end">{day}{order.pickup_window_label ? `, ${order.pickup_window_label}` : ""}</dd>
        <dt className="text-muted">{t("courier.cost")}</dt>
        <dd className="text-end text-2xl font-semibold tabular-nums">{money(pay.amount, pay.currency)}</dd>
      </dl>
      {waiting && <Alert tone="info" icon="hourglass" role="status">{t("payment.waiting")}</Alert>}
      {pay.status === "not_found" && <Alert tone="warning" role="status">{t("payment.notFound")}</Alert>}
      {pay.ways?.length ? (
        <PaymentWays pay={pay} busy={busy} amount={String(pay.amount)} onWay={onWay}
          copy={(label, value, mono) => <CopyRow label={label} value={value} mono={mono} />} transfer={transfer} />
      ) : (
        <>
          {transfer}
          {!waiting && <Button className="min-h-12 w-full" disabled={busy} icon="check" onClick={onClaim}>{t("payment.paid")}</Button>}
        </>
      )}
    </div>
  );
}

function CopyRow({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
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

/** заказан → забран → в пути → вручён → срок ответа → ответ получен, with the dates, the track number and
 *  «Загрузить ответ» once the document is handed over. */
function Timeline({ order, busy, onAnswer }: { order: CourierOrder; busy: boolean; onAnswer: (files: File[]) => void }) {
  const t = useT();
  const { lang } = useLang();
  const file = useRef<HTMLInputElement>(null);
  const at = (iso: string) => dateText(iso, lang, { time: true });
  const day = (iso: string) => dateText(iso.slice(0, 10), lang, { long: true });
  const reached = reachedStep(order.status);
  const refused = order.status === "refused" || order.events.some((e) => e.status === "refused");
  const when = (step: CourierStep) => order.events.find((e) => e.status === (step === "delivered" && refused ? "refused" : step))?.at;

  if (order.status === "cancelled") return <Alert tone="warning" role="status">{t("courier.st.cancelled")}</Alert>;

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted">{order.respondent_name} · {order.respondent_address}</p>
      <ol className="relative space-y-0">
        {COURIER_STEPS.map((step, i) => {
          const done = i <= reached;
          const current = i === reached + 1;
          const key = step === "delivered" && refused ? "refused" : step;
          const time = when(step);
          return (
            <li key={step} className="relative flex gap-3 pb-4 last:pb-0" aria-current={current ? "step" : undefined}>
              {i < COURIER_STEPS.length - 1 && (
                <span aria-hidden className={`absolute start-[11px] top-6 bottom-0 w-0.5 ${i < reached ? "bg-brand" : "bg-line"}`} />
              )}
              <span aria-hidden className={`relative z-10 flex h-6 w-6 shrink-0 items-center justify-center rounded-full ${
                done ? (key === "refused" ? "bg-danger-strong text-white" : "bg-brand-solid text-white")
                  : current ? "bg-surface ring-2 ring-brand" : "bg-surface ring-2 ring-line"}`}>
                {done && <Icon name={key === "refused" ? "x" : "check"} size={14} />}
              </span>
              <div className="min-w-0 flex-1 text-sm">
                <p className={done || current ? "font-semibold" : "text-muted"}>
                  {t(`courier.st.${key}`)}
                  {step === "answer_due" && order.answer_due_at && <span className="font-normal"> — {t("courier.answerDue", { date: day(order.answer_due_at) })}</span>}
                </p>
                {time && step !== "answer_due" && <p className="text-xs text-muted">{at(time)}</p>}
                {step === "ordered" && (
                  <p className="text-xs text-muted">{t("courier.pickupOn", { date: day(order.pickup_date), window: order.pickup_window_label ?? order.pickup_window })}</p>
                )}
                {step === "in_transit" && order.track_number && (
                  <p className="text-xs text-muted">
                    {order.carrier ? `${order.carrier} · ` : ""}{t("courier.track")}:{" "}
                    {order.track_url
                      ? <a className="font-mono underline" dir="ltr" href={order.track_url} target="_blank" rel="noreferrer">{order.track_number}</a>
                      : <span className="font-mono" dir="ltr">{order.track_number}</span>}
                  </p>
                )}
                {step === "delivered" && key === "refused" && reached >= 3 && <p className="mt-1 text-xs">{t("courier.refusedHint")}</p>}
                {step === "delivered" && reached >= 3 && (order.proof_files?.length ?? 0) > 0 && (
                  <ul className="mt-1 space-y-1">
                    {order.proof_files!.map((f) => (
                      <li key={f.url}>
                        <button type="button" className="inline-flex items-center gap-1 text-xs text-brand underline" onClick={() => downloadFile(f.url, f.name)}>
                          <Icon name="paperclip" size={14} />{t("courier.proof")}: {f.name}
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
                {step === "answer_due" && current && <p className="text-xs text-muted">{t("courier.answerDueHint")}</p>}
                {step === "answered" && order.status === "answered" && (order.answer_files?.length ?? 0) > 0 && (
                  <ul className="mt-1 space-y-1">
                    {order.answer_files!.map((f) => (
                      <li key={f.url}>
                        <button type="button" className="inline-flex items-center gap-1 text-xs text-brand underline" onClick={() => downloadFile(f.url, f.name)}>
                          <Icon name="paperclip" size={14} />{f.name}
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </li>
          );
        })}
      </ol>

      {reached === 3 && (
        <>
          <input ref={file} type="file" multiple accept="image/*,application/pdf,.doc,.docx" className="sr-only" tabIndex={-1} aria-hidden
            onChange={(e) => { const fs = Array.from(e.target.files ?? []); e.target.value = ""; if (fs.length) onAnswer(fs.slice(0, 5)); }} />
          <Button className="min-h-12 w-full" variant="secondary" icon="upload" disabled={busy} onClick={() => file.current?.click()}>
            {t("courier.uploadAnswer")}
          </Button>
          <p className="text-xs text-muted">{t("courier.uploadHint")}</p>
        </>
      )}
      {reached >= 3 && <p className="flex items-start gap-2 rounded-xl bg-sand p-3 text-xs"><Icon name="info" size={16} className="mt-0.5 shrink-0" />{t("courier.keepCopy")}</p>}
    </div>
  );
}
