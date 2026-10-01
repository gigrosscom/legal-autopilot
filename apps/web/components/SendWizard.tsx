"use client";

import { useEffect, useState } from "react";
import { CodeForm } from "@/components/CodeForm";
import { CourierDelivery } from "@/components/CourierDelivery";
import { EotinishBridge } from "@/components/EotinishBridge";
import { SignDocument } from "@/components/SignDocument";
import { Badge, Button, Icon, type IconName } from "@/components/ui";
import type { Tone } from "@/components/ui/Badge";
import {
  ApiError,
  api,
  applySignIn,
  downloadFile,
  errorText,
  fetchFile,
  saveBlob,
  type AuthMethods,
  type CaseAction,
  type CaseView,
  type Delivery,
  type EmailPreview,
  type FoundContact,
  type RouteStep,
  type SendGo,
  type SendPlan,
  type SignedIn,
} from "@/lib/api";
import { useLang, useT } from "@/lib/i18n";

type Channel = "whatsapp" | "telegram" | "instagram" | "email" | "app_dispute";
type Route = { key: string; channel: Channel; to: string; icon: IconName; href?: string };

const KIND_ICON: Record<FoundContact["kind"], IconName> = {
  whatsapp: "chat", phone: "phone", telegram: "send", instagram: "camera", email: "mail", website: "globe",
  bin: "landmark", address: "map",
};
const STATUS_TONE: Record<Delivery["status"], Tone> = {
  sending: "neutral", sent: "info", delivered: "brand", bounced: "danger", complained: "warning", failed: "danger",
};

const STEP_ICON: Record<RouteStep["channel"], IconName> = {
  email: "mail", whatsapp: "chat", telegram: "send", instagram: "camera", gov: "landmark", portal: "landmark", manual: "plus",
};

/** «Принцип 3 клика» (owner 01.10.2026): the server chooses where the document goes (e-mail to the address found
 *  in the case, one messenger, the appeal portal — eOtinish in KZ — for a state body); the client sees «Куда отправим»
 *  and presses ONE button. A portal step opens the portal bridge (EotinishBridge) right here: what to pick, the text,
 *  the PDF, then the number and date read from the portal's confirmation.
 *  With ЭЦП available the button signs first (the existing signing flow), then sends; without it the press itself
 *  is the client's instruction (consent text shown). E-mail goes at once; a messenger is one tap afterwards. */
export function SendWizard({ caseId, a, onCase }: { caseId: string; a: CaseAction; onCase?: (c: CaseView) => void }) {
  const t = useT();
  const { lang } = useLang();
  const base = `/v1/cases/${caseId}/actions/${a.id}`;
  const [plan, setPlan] = useState<SendPlan | null>(null);
  const [steps, setSteps] = useState<RouteStep[]>([]);
  const [deliveries, setDeliveries] = useState<Delivery[]>(a.filings ?? []);
  const [canSign, setCanSign] = useState(false);
  const [signing, setSigning] = useState(false);
  const [needEmail, setNeedEmail] = useState(false);
  const [sentNow, setSentNow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [portalOpen, setPortalOpen] = useState(false);
  const signed = (a.signatures ?? []).length > 0;

  useEffect(() => {
    let live = true;
    api<SendPlan>(`${base}/send`).then((p) => { if (!live) return; setPlan(p); setSteps(p.route); setDeliveries(p.filings); })
      .catch(() => { if (live) setPlan(null); });
    api<AuthMethods>("/v1/auth/methods").then((m) => { if (live) setCanSign(!!(m.ecp || m.egov)); }).catch(() => {});
    return () => { live = false; };
  }, [base]);

  const explain = (e: unknown) => {
    if (e instanceof ApiError && e.code) {
      const key = `send.errors.${e.code}`;
      const text = t(key);
      if (text !== key) return text;
    }
    return errorText(e);
  };

  const addDelivery = (f: Delivery) => setDeliveries((d) => [...d.filter((x) => x.id !== f.id), f]);

  async function go() {
    setBusy(true); setError(null); setSigning(false);
    try {
      const out = await api<SendGo>(`${base}/send/go`, { method: "POST", body: JSON.stringify({ confirm: true }) });
      out.sent.forEach(addDelivery);
      setSteps(out.steps);
      setSentNow(true);
      if (out.errors.length) setError(t(`send.errors.${out.errors[0].code}`));
      onCase?.(out.case);
    } catch (e) {
      if (e instanceof ApiError && e.code === "email_required") setNeedEmail(true);
      else setError(explain(e));
    } finally { setBusy(false); }
  }

  // a state body on the appeal portal: nothing goes by itself — the person files there in their own name, signing
  // with their own ЭЦП on the portal, so the button opens the portal bridge (no signing step here)
  const portalStep = steps.find((s) => s.channel === "portal");
  const portalOnly = !!portalStep && steps.every((s) => s.channel === "portal");
  const portalName = portalStep?.portal ?? "";
  const canFile = !!a.appeal_portal && !a.filed && !portalStep?.done;
  const press = () => (canSign && !signed ? setSigning(true) : go());
  const stepText = (s: RouteStep) => {
    if (s.channel === "gov") return t("send.plan.gov", { to: s.to });
    if (s.channel === "portal") return s.done ? t("send.plan.portalDone", { portal: s.portal ?? "" })
      : t("send.plan.portal", { portal: s.portal ?? "", to: s.to });
    if (s.channel === "manual") return t("send.plan.manual");
    if (s.channel === "email") return s.auto ? t("send.plan.emailAuto", { to: s.to }) : t("send.plan.emailOff", { to: s.to });
    return t("send.plan.messenger", { app: t(`send.channels.${s.channel}`), to: s.to });
  };

  if (!plan) return <Deliveries caseId={caseId} items={deliveries} onUpdate={addDelivery} lang={lang} />;
  const messengers = steps.filter((s) => ["whatsapp", "telegram", "instagram"].includes(s.channel));
  const gov = steps.find((s) => s.channel === "gov");
  return (
    <section className="space-y-3 rounded-2xl border border-line p-3" aria-label={t("send.plan.title")}>
      <div>
        <h4 className="font-semibold">{t("send.plan.title")}</h4>
        <ul className="mt-2 space-y-1.5">
          {steps.map((s) => (
            <li key={`${s.channel}-${s.to}`} className="flex items-start gap-2 text-sm">
              <Icon name={s.done ? "checkCircle" : STEP_ICON[s.channel]} size={18} className="mt-0.5 shrink-0 text-brand" />
              {s.channel === "portal" && canFile && !portalOpen
                ? <button type="button" className="min-w-0 break-words text-start underline decoration-dotted" onClick={() => setPortalOpen(true)}>{stepText(s)}</button>
                : <span className="min-w-0 break-words">{stepText(s)}</span>}
            </li>
          ))}
        </ul>
      </div>

      {needEmail ? (
        <div className="space-y-2 rounded-2xl bg-brand-50 p-3">
          <p className="text-sm">{t("send.needEmail")}</p>
          <CodeForm kind="email" wide onDone={(r: SignedIn) => { applySignIn(r); setNeedEmail(false); go(); }} />
        </div>
      ) : signing ? (
        <div className="space-y-2">
          <SignDocument base={base} fileBase={a.action_id} initial={a.signatures ?? []} canSign
            lead={t("send.plan.signLead")} onSigned={() => go()} />
          <button type="button" className="text-xs text-muted underline" disabled={busy} onClick={go}>{t("send.plan.noSign")}</button>
        </div>
      ) : portalOnly ? (canFile && !portalOpen && (
        <Button className="min-h-12 w-full" icon="landmark" onClick={() => setPortalOpen(true)}>
          {t("send.plan.portalGo", { portal: portalName })}
        </Button>
      )) : !sentNow && (
        <div className="space-y-2">
          <p className="text-xs text-muted">{t("send.consent")}</p>
          <Button className="min-h-12 w-full" icon={busy ? "spinner" : canSign && !signed ? "key" : "send"} disabled={busy} onClick={press}>
            {canSign && !signed ? t("send.plan.signAndSend") : t("send.plan.send")}
          </Button>
        </div>
      )}
      {portalOpen && canFile && <EotinishBridge caseId={caseId} a={a} onCase={onCase} startOpen />}

      {sentNow && messengers.map((s) => (
        <MessengerSend key={s.channel} base={base} a={a} text={plan.message} channel={s.channel as Channel} to={s.to}
          href={s.href ?? undefined} explain={explain}
          onDone={(out) => { addDelivery(out.filing); if (out.case) onCase?.(out.case); }} />
      ))}
      {sentNow && gov && <p className="rounded-2xl bg-brand-50 p-3 text-sm">{t("send.plan.govNext")}</p>}
      {error && <p role="alert" className="text-xs text-danger">{error}</p>}

      <Deliveries caseId={caseId} items={deliveries} onUpdate={addDelivery} lang={lang} />
      {/* «Доставить курьером» (pilot «Курьер»): the paper copy handed over against a signature, paid like the document */}
      {!portalOnly && <CourierDelivery caseId={caseId} a={a} onCase={onCase} />}
      <details className="rounded-2xl border border-line px-3 py-2">
        <summary className="cursor-pointer text-sm">{t("send.plan.other")}</summary>
        <div className="pt-2">
          <ManualSend caseId={caseId} a={a} onCase={onCase} onDelivery={addDelivery} />
        </div>
      </details>
    </section>
  );
}

/** Other ways and a typed address (fallback): we find the other side's contacts in the case, the client picks the
 *  fastest way and sends it themselves — from their own WhatsApp / Telegram / Instagram (we never message third
 *  parties), or by e-mail through our service (Reply-To and a copy to them). Each sending is kept as proof:
 *  Resend's statuses for e-mail, the client's screenshot for a messenger. The response deadline starts from it. */
function ManualSend({ caseId, a, onCase, onDelivery }: {
  caseId: string; a: CaseAction; onCase?: (c: CaseView) => void; onDelivery: (f: Delivery) => void;
}) {
  const t = useT();
  const base = `/v1/cases/${caseId}/actions/${a.id}`;
  const [plan, setPlan] = useState<SendPlan | null>(null);
  const [route, setRoute] = useState<Route | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [manual, setManual] = useState("");

  const explain = (e: unknown) => {
    if (e instanceof ApiError && e.code) {
      const key = `send.errors.${e.code}`;
      const text = t(key);
      if (text !== key) return text;
    }
    return errorText(e);
  };

  async function open() {
    setBusy(true); setError(null);
    try {
      const p = await api<SendPlan>(`${base}/send`);
      setPlan(p);
    } catch (e) { setError(explain(e)); } finally { setBusy(false); }
  }

  function done(out: { filing: Delivery; case?: CaseView }) {
    onDelivery(out.filing);
    if (out.case) onCase?.(out.case);
    setRoute(null);
  }

  const copy = async (text: string) => {
    try { await navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 2000); } catch { /* no clipboard */ }
  };

  // The PDF goes through the phone's share sheet (the client picks the chat); on a computer it is downloaded to attach.
  const routes = (contacts: FoundContact[], extra: string): Route[] => {
    const list: Route[] = [];
    const msg = plan?.message ?? "";
    const phones = contacts.filter((c) => c.kind === "whatsapp" || c.kind === "phone").map((c) => c.value);
    const emails = contacts.filter((c) => c.kind === "email").map((c) => c.value);
    const typed = extra.trim();
    if (/^\+?[\d\s()-]{10,}$/.test(typed)) phones.push(typed.startsWith("+") ? typed.replace(/[^\d+]/g, "") : `+${typed.replace(/\D/g, "")}`);
    if (/^[^\s@,;]+@[^\s@,;]+\.[^\s@,;]+$/.test(typed)) emails.push(typed.toLowerCase());
    for (const p of [...new Set(phones)])
      list.push({ key: `wa-${p}`, channel: "whatsapp", to: p, icon: "chat",
        href: `https://wa.me/${p.replace(/\D/g, "")}?text=${encodeURIComponent(msg)}` });
    for (const c of contacts.filter((x) => x.kind === "telegram"))
      list.push({ key: `tg-${c.value}`, channel: "telegram", to: `@${c.value}`, icon: "send", href: `https://t.me/${c.value}` });
    for (const c of contacts.filter((x) => x.kind === "instagram"))
      list.push({ key: `ig-${c.value}`, channel: "instagram", to: `@${c.value}`, icon: "camera", href: `https://ig.me/m/${c.value}` });
    for (const e of [...new Set(emails)]) list.push({ key: `em-${e}`, channel: "email", to: e, icon: "mail" });
    list.push({ key: "em-new", channel: "email", to: "", icon: "mail" });
    list.push({ key: "dispute", channel: "app_dispute", to: "", icon: "coin" });
    return list;
  };

  const source = (s: FoundContact["sources"][number]) =>
    s.type === "evidence" ? t("send.src.evidence", { label: s.label ?? s.filename ?? "" })
      : s.type === "story" ? t("send.src.story") : t("send.src.case");

  if (!plan) {
    return (
      <div className="space-y-2">
        <Button className="w-full" variant="secondary" icon={busy ? "spinner" : "send"} disabled={busy} onClick={open}>{t("send.open")}</Button>
        {error && <p role="alert" className="text-xs text-danger">{error}</p>}
      </div>
    );
  }

  const contacts = plan.contacts;
  const site = contacts.find((c) => c.kind === "website");
  return (
    <section className="space-y-4 rounded-2xl border border-line p-3" aria-label={t("send.title")}>
      <div className="flex items-start justify-between gap-2">
        <div>
          <h4 className="font-semibold">{t("send.title")}</h4>
          <p className="text-xs text-muted">{t("send.lead")}</p>
        </div>
        <button type="button" className="p-1 text-muted" aria-label={t("app.cancel")} onClick={() => { setPlan(null); setRoute(null); }}>
          <Icon name="x" size={18} />
        </button>
      </div>

      <div className="space-y-2">
        <p className="text-sm font-semibold">1. {t("send.whom")}</p>
        {contacts.length === 0 && <p className="text-sm text-muted">{t("send.nothingFound")}</p>}
        <ul className="space-y-1.5">
          {contacts.map((c) => (
            <li key={`${c.kind}-${c.value}`} className="flex items-start gap-2 text-sm">
              <Icon name={KIND_ICON[c.kind]} size={16} className="mt-0.5 shrink-0 text-brand" />
              <span className="min-w-0">
                <span className="break-all font-medium">{c.kind === "telegram" || c.kind === "instagram" ? `@${c.value}` : c.value}</span>
                <span className="block text-xs text-muted">{t(`send.kinds.${c.kind}`)} · {c.sources.map(source).join(", ")}</span>
              </span>
            </li>
          ))}
        </ul>
        {site && (
          <p className="flex items-start gap-1.5 text-xs text-muted">
            <Icon name="info" size={14} className="mt-0.5 shrink-0" />
            <span>{t("send.siteHint")} <a className="underline" href={`https://${site.value}`} target="_blank" rel="noreferrer">{site.value}</a></span>
          </p>
        )}
        <label className="block text-xs text-muted" htmlFor={`manual-${a.id}`}>{t("send.manual")}</label>
        <input id={`manual-${a.id}`} className="input" value={manual} maxLength={254} inputMode="email"
          placeholder={t("send.manualPlaceholder")} onChange={(e) => setManual(e.target.value)} />
      </div>

      <div className="space-y-2">
        <p className="text-sm font-semibold">2. {t("send.how")}</p>
        <div className="grid gap-2 sm:grid-cols-2">
          {routes(contacts, manual).map((r) => (
            <button key={r.key} type="button" onClick={() => { setRoute(r); setError(null); }}
              className={`flex min-h-12 items-center gap-2 rounded-2xl border px-3 py-2 text-start text-sm ${route?.key === r.key ? "border-brand bg-brand-50 text-brand" : "border-line bg-surface hover:border-brand"}`}>
              <Icon name={r.icon} size={18} className="shrink-0" />
              <span className="min-w-0">
                <span className="block font-medium">{t(`send.channels.${r.channel}`)}{r.key === "em-new" ? ` — ${t("send.otherAddress")}` : ""}</span>
                {r.to && <span className="block truncate text-xs text-muted">{r.to}</span>}
              </span>
            </button>
          ))}
        </div>
      </div>

      {route && (route.channel === "email"
        ? <EmailStep key={route.key} base={base} initial={route.to} plan={plan} onSent={done} explain={explain} />
        : (
          <div className="space-y-2 rounded-2xl bg-brand-50 p-3">
            {route.channel === "app_dispute" && <p className="text-sm">{t("send.disputeHow")}</p>}
            <p className="text-xs text-muted">{t("send.shortText")}</p>
            <pre className="whitespace-pre-wrap rounded-xl bg-surface p-2 text-sm">{plan.message}</pre>
            <Button variant="secondary" icon={copied ? "check" : "copy"} onClick={() => copy(plan.message)}>{copied ? t("send.copied") : t("send.copy")}</Button>
            {route.channel === "app_dispute"
              ? <ProofStep base={base} route={route} onDone={done} explain={explain} />
              : <MessengerSend base={base} a={a} text={plan.message} channel={route.channel} to={route.to} href={route.href}
                  explain={explain} onDone={done} />}
          </div>
        ))}
      {error && <p role="alert" className="text-xs text-danger">{error}</p>}
    </section>
  );
}

/** E-mail through our service: the address, the letter as it will go, then «Отправить». */
function EmailStep({ base, initial, plan, onSent, explain }: {
  base: string; initial: string; plan: SendPlan; onSent: (out: { filing: Delivery; case?: CaseView }) => void;
  explain: (e: unknown) => string;
}) {
  const t = useT();
  const [to, setTo] = useState(initial);
  const [preview, setPreview] = useState<EmailPreview | null>(null);
  const [needEmail, setNeedEmail] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const state = plan.email;

  async function show(e?: React.FormEvent) {
    e?.preventDefault();
    setBusy(true); setError(null);
    try {
      setPreview(await api<EmailPreview>(`${base}/email/preview`, { method: "POST", body: JSON.stringify({ to }) }));
    } catch (err) {
      if (err instanceof ApiError && err.code === "email_required") setNeedEmail(true);
      else setError(explain(err));
    } finally { setBusy(false); }
  }

  async function send() {
    if (!preview) return;
    setBusy(true); setError(null);
    try {
      onSent(await api<{ filing: Delivery; case: CaseView }>(`${base}/email`, {
        method: "POST", body: JSON.stringify({ to: preview.to, confirm: true }),
      }));
    } catch (err) { setError(explain(err)); } finally { setBusy(false); }
  }

  if (!state.available && state.reason) {
    return <p className="rounded-2xl bg-brand-50 p-3 text-sm">{t(`send.errors.${state.reason}`)}</p>;
  }
  if (needEmail) {
    return (
      <div className="space-y-2 rounded-2xl bg-brand-50 p-3">
        <p className="text-sm">{t("send.needEmail")}</p>
        <CodeForm kind="email" wide onDone={(r: SignedIn) => { applySignIn(r); setNeedEmail(false); show(); }} />
      </div>
    );
  }
  return (
    <div className="space-y-3 rounded-2xl bg-brand-50 p-3">
      {!preview ? (
        <form className="space-y-2" onSubmit={show}>
          <label className="block text-sm" htmlFor="send-to">{t("send.emailTo")}</label>
          <input id="send-to" className="input" type="email" inputMode="email" autoComplete="off" required maxLength={254}
            value={to} onChange={(e) => setTo(e.target.value)} placeholder="name@company.kz" />
          <p className="text-xs text-muted">{t("send.emailHint", { n: String(state.left) })}</p>
          <Button className="min-h-12 w-full" icon={busy ? "spinner" : "mail"} disabled={busy || !to.trim()}>{t("send.preview")}</Button>
        </form>
      ) : (
        <div className="space-y-2">
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
            <dt className="text-muted">{t("send.from")}</dt><dd className="break-all">{preview.from}</dd>
            <dt className="text-muted">{t("send.to")}</dt><dd className="break-all font-semibold">{preview.to}</dd>
            <dt className="text-muted">{t("send.replyTo")}</dt><dd className="break-all">{preview.reply_to}</dd>
            <dt className="text-muted">{t("send.cc")}</dt><dd className="break-all">{preview.cc}</dd>
            <dt className="text-muted">{t("send.subject")}</dt><dd>{preview.subject}</dd>
          </dl>
          <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded-xl bg-surface p-2 text-sm">{preview.text}</pre>
          <ul className="space-y-0.5 text-xs">
            {preview.attachments.map((f) => (
              <li key={f.name} className="flex items-center gap-1.5"><Icon name="paperclip" size={14} />{f.name} · {Math.max(1, Math.round(f.size / 1024))} KB</li>
            ))}
          </ul>
          <p className="text-xs text-muted">{t("send.consent")}</p>
          <div className="flex gap-2">
            <Button className="min-h-12 flex-1" icon={busy ? "spinner" : "send"} disabled={busy} onClick={send}>{t("send.sendNow")}</Button>
            <Button className="min-h-12" variant="secondary" disabled={busy} onClick={() => setPreview(null)}>{t("send.change")}</Button>
          </div>
        </div>
      )}
      {error && <p role="alert" className="text-xs text-danger">{error}</p>}
    </div>
  );
}

/** One «Отправить» to a messenger: the share sheet carries the PDF and the short text into the chosen chat (phone);
 *  elsewhere the chat opens with the text and the PDF is saved to attach. The time of the press is kept as the sending
 *  time; a screenshot «доставлено / прочитано» can be added afterwards as proof. */
function MessengerSend({ base, a, text, channel, to, href, explain, onDone }: {
  base: string; a: CaseAction; text: string; channel: Channel; to: string; href?: string;
  explain: (e: unknown) => string; onDone: (out: { filing: Delivery; case?: CaseView }) => void;
}) {
  const t = useT();
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fmt = a.has_pdf ? "pdf" : "docx";
  async function send() {
    setBusy(true); setError(null);
    const win = href ? window.open("about:blank", "_blank") : null;  // opened now, inside the click, so it isn't blocked
    try {
      const blob = await fetchFile(`${base}/document?format=${fmt}`);
      const file = new File([blob], `${a.action_id}.${fmt}`, { type: blob.type || "application/pdf" });
      const nav = navigator as Navigator & { canShare?: (d: ShareData) => boolean };
      if (nav.share && nav.canShare?.({ files: [file] })) {
        win?.close();
        try { await nav.share({ files: [file], text, title: a.title }); } catch { setBusy(false); return; }  // cancelled
      } else {
        if (win && href) win.location.href = href; else if (href) window.open(href, "_blank");
        saveBlob(blob, file.name);
      }
      const form = new FormData();
      form.append("channel", channel);
      form.append("recipient", to);
      onDone(await api<{ filing: Delivery; case: CaseView }>(`${base}/send/proof`, { method: "POST", body: form }));
      setSent(true);
    } catch (e) { win?.close(); setError(explain(e)); } finally { setBusy(false); }
  }
  return (
    <div className="space-y-2 rounded-2xl bg-brand-50 p-3">
      <Button className="min-h-12 w-full" icon={busy ? "spinner" : (STEP_ICON as Partial<Record<string, IconName>>)[channel] ?? "send"} disabled={busy || sent} onClick={send}>
        {sent ? t("send.sentTo", { app: t(`send.channels.${channel}`) }) : t("send.sendTo", { app: t(`send.channels.${channel}`) })}
      </Button>
      {error && <p role="alert" className="text-xs text-danger">{error}</p>}
    </div>
  );
}

/** «Я отправил»: the time is kept; a screenshot «доставлено / прочитано» is the proof (now or later). */
function ProofStep({ base, route, onDone, explain }: {
  base: string; route: Route; onDone: (out: { filing: Delivery; case?: CaseView }) => void; explain: (e: unknown) => string;
}) {
  const t = useT();
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function confirm() {
    setBusy(true); setError(null);
    const form = new FormData();
    form.append("channel", route.channel);
    form.append("recipient", route.to);
    if (file) form.append("file", file);
    try { onDone(await api<{ filing: Delivery; case: CaseView }>(`${base}/send/proof`, { method: "POST", body: form })); }
    catch (e) { setError(explain(e)); } finally { setBusy(false); }
  }
  return (
    <div className="space-y-2 border-t border-line pt-2">
      <p className="text-xs text-muted">{t("send.proofHint")}</p>
      <label className="btn-ghost cursor-pointer">
        <Icon name="camera" size={18} />{file ? file.name : t("send.screenshot")}
        <input type="file" accept="image/*,application/pdf" className="sr-only" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
      </label>
      <Button className="min-h-12 w-full" icon={busy ? "spinner" : "check"} disabled={busy} onClick={confirm}>
        {route.channel === "app_dispute" ? t("send.disputeDone") : t("send.iSent")}
      </Button>
      {error && <p role="alert" className="text-xs text-danger">{error}</p>}
    </div>
  );
}

/** What has gone, with its proof: Resend's status for e-mail, the client's screenshot for a messenger. */
function Deliveries({ caseId, items, onUpdate, lang }: {
  caseId: string; items: Delivery[]; onUpdate: (f: Delivery) => void; lang: string;
}) {
  const t = useT();
  const [busy, setBusy] = useState<string | null>(null);
  if (!items.length) return null;
  const when = (iso: string | null) => iso ? new Date(iso).toLocaleString(lang === "ar" ? "ar" : lang === "en" ? "en-GB" : "ru-RU",
    { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "";
  async function upload(f: Delivery, file: File) {
    setBusy(f.id);
    const form = new FormData();
    form.append("file", file);
    try { onUpdate((await api<{ filing: Delivery }>(`/v1/cases/${caseId}/filings/${f.id}/receipt`, { method: "POST", body: form })).filing); }
    catch { /* shown as not uploaded */ } finally { setBusy(null); }
  }
  return (
    <div className="space-y-1.5">
      <p className="text-sm font-semibold">{t("send.sentList")}</p>
      <ul className="space-y-1.5">
        {items.map((f) => (
          <li key={f.id} className="rounded-xl border border-line p-2 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium">{t(`send.channels.${f.channel}`)}</span>
              {f.recipient && <span className="break-all text-muted">{f.recipient}</span>}
              <Badge tone={STATUS_TONE[f.status]}>{t(f.channel === "email" ? `send.status.${f.status}` : "send.status.reported")}</Badge>
              {f.replied_at && <Badge tone="brand" icon="mail">{t("send.status.replied")}</Badge>}
              <span className="ms-auto text-xs tabular-nums text-muted">{when(f.delivered_at ?? f.sent_at ?? f.created_at)}</span>
            </div>
            {f.channel !== "email" && (
              <div className="mt-1 flex flex-wrap items-center gap-2 text-xs">
                {f.has_receipt && (
                  <button type="button" className="flex items-center gap-1 text-brand underline"
                    onClick={() => downloadFile(`/v1/cases/${caseId}/filings/${f.id}/receipt`, `receipt-${f.id}`)}>
                    <Icon name="shieldCheck" size={14} />{t("send.receiptSaved")}
                  </button>
                )}
                <label className={`cursor-pointer text-muted underline ${busy === f.id ? "opacity-50" : ""}`}>
                  {f.has_receipt ? t("send.receiptMore") : t("send.receiptAdd")}
                  <input type="file" accept="image/*,application/pdf" className="sr-only" disabled={busy === f.id}
                    onChange={(e) => { const x = e.target.files?.[0]; e.target.value = ""; if (x) upload(f, x); }} />
                </label>
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
