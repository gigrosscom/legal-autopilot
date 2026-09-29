"use client";

import { useEffect, useState } from "react";
import { Alert, Button, Icon } from "@/components/ui";
import { api, ApiError, errorText, type CaseView } from "@/lib/api";
import { useLang, useT } from "@/lib/i18n";

type Msg = { id: number; author: "client" | "desk"; text: string; created_at: string };
export type Ticket = { id: number; kind: string; status: string; created_at: string; case_id: string | null; messages: Msg[] };
const KINDS = ["question", "complaint", "suggestion", "data"] as const;  // data: a personal data request
/** Plans that are not paid online yet: the home page links here with ?plan=…, the ticket goes to the clients desk. */
const PLANS = ["case", "biz", "bizpro"] as const;
type Kind = (typeof KINDS)[number] | "plan";

/** Write to Konsiliér AI: a question, a complaint, a suggestion or a personal data request. Replies come by e-mail and show here. */
export default function SupportPage() {
  const t = useT();
  const { lang } = useLang();
  const [kind, setKind] = useState<Kind>("question");
  const [plan, setPlan] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [caseId, setCaseId] = useState("");
  const [cases, setCases] = useState<CaseView[]>([]);
  const [mine, setMine] = useState<Ticket[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState<number | null>(null);

  const load = () => api<Ticket[]>("/v1/support").then(setMine).catch(() => {});
  useEffect(() => {
    load();
    api<CaseView[]>("/v1/cases").then(setCases).catch(() => {});
    const k = new URLSearchParams(window.location.search).get("kind");
    if (k && (KINDS as readonly string[]).includes(k)) setKind(k as (typeof KINDS)[number]);
    const p = new URLSearchParams(window.location.search).get("plan");
    if (p && (PLANS as readonly string[]).includes(p)) {
      setPlan(p);
      setKind("plan");
      setText(t("support.planText", { plan: t(`home.price.${p}T`) }));
    }
    const c = new URLSearchParams(window.location.search).get("case");
    if (c) setCaseId(c);
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      const out = await api<Ticket>("/v1/support", { method: "POST", body: JSON.stringify({
        kind, text: text.trim(), name: name.trim() || null, email: email.trim() || null, phone: phone.trim() || null,
        case_id: caseId || null, language: lang }) });
      setSent(out.id); setText(""); load();
      window.scrollTo({ top: 0 });
    } catch (err) { setError(err instanceof ApiError && err.code === "contact_required" ? t("support.contactHint") : errorText(err)); } finally { setBusy(false); }
  }

  const field = "input mt-1 min-h-12 text-base";
  return (
    <div className="mx-auto max-w-xl space-y-6">
      <div className="space-y-2">
        <h1 className="text-3xl font-semibold tracking-tight">{t("support.title")}</h1>
        <p className="text-muted">{t("support.lead")}</p>
      </div>
      {sent && <Alert tone="info" icon="checkCircle" title={t("support.sentTitle", { n: sent })}>{t("support.sentText")}</Alert>}

      <form onSubmit={submit} className="card space-y-4">
        {plan ? (
          <p className="rounded-2xl bg-brand-50 px-4 py-3 font-semibold text-ink">{t("support.planTitle", { plan: t(`home.price.${plan}T`) })}</p>
        ) : <div role="radiogroup" aria-label={t("support.kind")} className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {KINDS.map((k) => (
            <button key={k} type="button" role="radio" aria-checked={kind === k} onClick={() => setKind(k)}
              className={`min-h-12 rounded-2xl border px-1 text-[13px] font-semibold sm:text-sm ${kind === k ? "border-brand bg-brand text-white" : "border-line bg-surface hover:border-brand"}`}>
              {t(`support.kinds.${k}`)}
            </button>
          ))}
        </div>}
        <label className="block text-sm font-semibold">{t(`support.textLabel.${kind}`)}
          <textarea className="input mt-1 min-h-32 text-base font-normal" required minLength={5} maxLength={4000}
            value={text} onChange={(e) => setText(e.target.value)} />
        </label>
        {cases.length > 0 && (
          <label className="block text-sm">{t("support.case")}
            <select className={field} value={caseId} onChange={(e) => setCaseId(e.target.value)}>
              <option value="">{t("support.noCase")}</option>
              {cases.map((c) => <option key={c.id} value={c.id}>{c.scenario?.title ?? c.coverage?.dispute?.title ?? t("case.untitled")}</option>)}
            </select>
          </label>
        )}
        <fieldset className="space-y-3">
          <legend className="text-sm font-semibold">{t("support.contacts")}</legend>
          <label className="block text-sm">{t("request.name")}
            <input className={field} autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} />
          </label>
          <label className="block text-sm">E-mail
            <input className={field} type="email" inputMode="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
          </label>
          <label className="block text-sm">{t("request.phone")}
            <input className={field} type="tel" inputMode="tel" autoComplete="tel" placeholder="+7 700 000 00 00" value={phone} onChange={(e) => setPhone(e.target.value)} />
          </label>
          {phone.trim() && !email.trim()
            ? <p className="text-xs text-warning" role="status">{t("support.phoneOnly")}</p>
            : <p className="text-xs text-muted">{t("support.contactHint")}</p>}
        </fieldset>
        {error && <Alert tone="danger" role="alert">{error}</Alert>}
        <Button size="lg" className="w-full" disabled={busy || text.trim().length < 5 || !(email.trim() || phone.trim())} icon={busy ? "spinner" : "send"}>
          {t("support.send")}
        </Button>
      </form>

      {mine.length > 0 && (
        <section className="space-y-3" aria-labelledby="mine">
          <h2 id="mine" className="text-lg font-semibold">{t("support.mine")}</h2>
          {mine.map((tk) => <TicketThread key={tk.id} tk={tk} onReply={load} />)}
        </section>
      )}
    </div>
  );
}

function TicketThread({ tk, onReply }: { tk: Ticket; onReply: () => void }) {
  const t = useT();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  async function send() {
    setBusy(true);
    try { await api(`/v1/support/${tk.id}/messages`, { method: "POST", body: JSON.stringify({ text }) }); setText(""); onReply(); }
    finally { setBusy(false); }
  }
  return (
    <article className="card space-y-3 text-sm">
      <p className="flex flex-wrap items-center gap-2">
        <b>{t(`support.kinds.${tk.kind}`)} №{tk.id}</b>
        <span className="chip">{t(`support.status.${tk.status}`)}</span>
        <span className="text-xs text-muted">{new Date(tk.created_at).toLocaleDateString("ru-RU")}</span>
      </p>
      {tk.messages.map((m) => (
        <div key={m.id} className={`rounded-2xl px-3 py-2 ${m.author === "desk" ? "bg-brand-50" : "bg-sand"}`}>
          <p className="text-xs font-semibold text-muted">{m.author === "desk" ? t("support.team") : t("support.you")}</p>
          <p className="whitespace-pre-line">{m.text}</p>
        </div>
      ))}
      {tk.messages.some((m) => m.author === "desk") && (
        <div className="flex items-end gap-2">
          <textarea className="input min-h-12 flex-1" rows={1} value={text} onChange={(e) => setText(e.target.value)}
            placeholder={t("support.replyPlaceholder")} aria-label={t("support.replyPlaceholder")} />
          <button type="button" disabled={busy || !text.trim()} onClick={send} aria-label={t("case.send")}
            className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-brand text-white disabled:opacity-40">
            <Icon name={busy ? "spinner" : "send"} size={18} />
          </button>
        </div>
      )}
    </article>
  );
}
