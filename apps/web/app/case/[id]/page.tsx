"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { EmergencyPanel } from "@/components/EmergencyPanel";
import { BetaNotice } from "@/components/BetaNotice";
import { AnswerBar } from "@/components/AnswerBar";
import { AppShell, type MoreLink, type MoreSection } from "@/components/AppShell";
import { CodeForm } from "@/components/CodeForm";
import { Invite } from "@/components/Invite";
import { LevelBadge, LevelExplainer } from "@/components/LevelBadge";
import RoadmapView from "@/components/Roadmap";
import { SignDocument } from "@/components/SignDocument";
import { SendWizard } from "@/components/SendWizard";
import { ChooseLawyer } from "@/components/ChooseLawyer";
import { Agreements } from "@/components/Agreements";
import { Bubble } from "@/components/Bubble";
import { DraftPreview, draftSaved } from "@/components/DraftPreview";
import { EotinishBridge, EotinishFiled } from "@/components/EotinishBridge";
import { FilePicker } from "@/components/FilePicker";
import { GovServices } from "@/components/GovServices";
import { LawQuestions } from "@/components/LawQuestions";
import { KaspiOneTap, kaspiOneTap, PaymentWays, type WayBody } from "@/components/PaymentWays";
import { StageProgress } from "@/components/StageProgress";
import { Alert, Badge, Button, Icon, type IconName } from "@/components/ui";
import {
  ApiError,
  api,
  applySignIn,
  downloadFile,
  errorText,
  fetchFile,
  saveBlob,
  type CaseAction,
  type CaseLawyer,
  type Filing,
  type Me,
  type CaseView,
  type Emergency,
  type ForumOption,
  type Proposal,
  type Reply,
  printFile,
  shareFile,
  type Plan,
  type Payment,
  type SignedIn,
  saveFileAs,
} from "@/lib/api";
import { LAWYERS_PUBLIC, LAWYER_PILOT } from "@/lib/features";
import { LawyerPilot } from "@/components/LawyerPilot";
import { useLang, useT } from "@/lib/i18n";

type Msg = { from: "bot" | "user"; text: string };

// Question texts are shared with the Telegram bot, where people type everything («пропустить», dates as
// ДД.ММ.ГГГГ). On the web the calendar and the «Пропустить» button do that, so those typing hints are hidden.
const SKIP_WORD = /«(пропустить|өткізу|skip|atla|تخطي)»/i;
function forScreen(text: string): string {
  const out = text
    .replace(/\s*\((ДД\.ММ\.ГГГГ|КК\.АА\.ЖЖЖЖ|DD\.MM\.YYYY|GG\.AA\.YYYY)\)/g, "")
    .split(/(?<=[.?!])(\s+)/)  // sentences with the spaces / line breaks after them kept as separate items
    .reduce((acc: string[], part, i, all) => (i % 2 === 0 && !SKIP_WORD.test(part) ? [...acc, part, all[i + 1] ?? ""] : acc), [])
    .join("").trim();
  return out || text;
}

function saveReply(id: string, reply: Reply) {
  try {
    sessionStorage.setItem(`konsilier.reply.${id}`, JSON.stringify(reply));
  } catch {}
}

function readStoredReply(id: string): Partial<Reply> | null {
  try {
    const raw = sessionStorage.getItem(`konsilier.reply.${id}`);
    if (!raw) return null;
    return raw.startsWith("{") ? (JSON.parse(raw) as Reply) : { message: raw };
  } catch {
    return null;
  }
}

export default function CasePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [pilotStatus, setPilotStatus] = useState<string | null>(null);  // «Юрист по кнопке»: refreshes the lawyer block
  // owner 30.09: the «Юрист» tab is hidden while the pilot has no lawyers (unless this case already has a request)
  const [pilotOpen, setPilotOpen] = useState(false);
  useEffect(() => {
    if (!LAWYER_PILOT || !id) return;
    api<{ lawyers: unknown[]; request: unknown; last: unknown }>(`/v1/cases/${id}/lawyers`)
      .then((v) => setPilotOpen(v.lawyers.length > 0 || !!v.request || !!v.last)).catch(() => setPilotOpen(false));
  }, [id]);
  const t = useT();
  const [c, setCase] = useState<CaseView | null>(null);
  const [log, setLog] = useState<Msg[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [emergency, setEmergency] = useState<Emergency | null>(null);

  const [payOpen, setPayOpen] = useState(false);
  const [chooseOpen, setChooseOpen] = useState(false);  // «Выбрать юриста» (owner 02.10)
  // the server asks for a confirmed contact before the first bill: the payment window shows that step first
  const [contact, setContact] = useState<{ kind: "phone" | "email"; purpose: string } | null>(null);
  // PM 01.10: the applicant's own data (name, IIN, address, phone) on one screen right before paying
  const [applicant, setApplicant] = useState<{ fields: ApplicantField[]; purpose: string } | null>(null);

  const push = (m: Msg) => setLog((l) => [...l, m]);

  useEffect(() => {
    api<CaseView>(`/v1/cases/${id}`)
      .then((view) => {
        setCase(view);
        const first = readStoredReply(id);
        const initial: Msg[] = [];
        // The stored reply may be stale (e.g. "tell me more" before the case was qualified):
        // show it only if it still leads to the question the case is waiting for.
        if (first?.message && (!view.question || first.message.includes(view.question.text)))
          initial.push({ from: "bot", text: first.message });
        else if (view.question) initial.push({ from: "bot", text: view.question.text });
        if (first?.emergency) setEmergency(first.emergency);
        setLog(initial);
      })
      .catch((e) => setError(errorText(e)));
  }, [id]);

  const run = useCallback(async (fn: () => Promise<void>): Promise<boolean> => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      return true;
    } catch (e) {
      setError(errorText(e));
      return false;
    } finally {
      setBusy(false);
    }
  }, []);

  function applyReply(out: { case: CaseView; reply: Reply }) {
    setCase(out.case);
    if (out.reply.message) {
      push({ from: "bot", text: out.reply.message });
      saveReply(id, out.reply);
    }
  }

  async function sendAnswer(text: string, shown?: string): Promise<boolean> {
    const ok = await run(async () => {
      push({ from: "user", text: shown ?? text });
      applyReply(await api<{ case: CaseView; reply: Reply }>(`/v1/cases/${id}/messages`, {
        method: "POST", body: JSON.stringify({ text }),
      }));
    });
    if (!ok) {
      // Not delivered (bad connection): take the message back into the input so nothing is lost.
      setLog((l) => (l.at(-1)?.from === "user" && l.at(-1)?.text === (shown ?? text) ? l.slice(0, -1) : l));
    }
    return ok;
  }

  async function chooseForum(f: ForumOption) {
    await run(async () => {
      push({ from: "user", text: f.name });
      applyReply(await api<{ case: CaseView; reply: Reply }>(`/v1/cases/${id}/forum`, {
        method: "POST", body: JSON.stringify({ forum_id: f.id }),
      }));
    });
  }

  async function acknowledge(kind: string) {
    await run(async () => {
      applyReply(await api<{ case: CaseView; reply: Reply }>(`/v1/cases/${id}/acknowledge`, {
        method: "POST", body: JSON.stringify({ kind }),
      }));
    });
  }

  // Documents are read at once: what they show goes into the case and is never asked; the reply says what was
  // taken from each file, then asks only what is still missing (once, after the last file).
  async function upload(files: File[]) {
    await run(async () => {
      for (const [i, file] of files.entries()) {
        const kind = c?.question?.type === "evidence" ? c.question.evidence_kinds?.[0]?.kind ?? "other" : "other";
        const form = new FormData();
        form.append("file", file);
        form.append("kind", kind);
        push({ from: "user", text: `📎 ${file.name}` });
        const out = await api<{ case: CaseView; reply: Reply }>(`/v1/cases/${id}/evidence`, { method: "POST", body: form });
        setCase(out.case);
        const q = out.reply.question?.text;
        const last = i === files.length - 1;
        const text = !last && q && out.reply.message?.endsWith(q) ? out.reply.message.slice(0, -q.length).trim() : out.reply.message;
        if (text) push({ from: "bot", text });
        if (last && out.reply.message) saveReply(id, out.reply);
      }
    });
  }

  async function post(path: string, body: unknown = {}) {
    await run(async () => {
      const out = await api<{ case: CaseView; proposal?: Proposal; payment?: unknown }>(`/v1/cases/${id}${path}`, {
        method: "POST", body: JSON.stringify(body),
      });
      setCase(out.case);
      if (out.payment) setPayOpen(true);  // the document needs paying first: the payment window opens at once
      if (path === "/actions/next" && !out.payment) setPayOpen(false);
    });
  }

  async function choosePayment(purpose: string) {
    await draftSaved();  // what was just typed in the draft's blanks is in the case first: never asked twice (PM 02.10)
    await run(async () => {
      try {
        const out = await api<{ case: CaseView }>(`/v1/cases/${id}/payment`, { method: "POST", body: JSON.stringify({ purpose }) });
        setCase(out.case);
      } catch (e) {
        if (e instanceof ApiError && e.code === "applicant_data_required") {
          setApplicant({ fields: (e.detail as { fields?: ApplicantField[] }).fields ?? [], purpose });
          setPayOpen(true);
          return;
        }
        if (!(e instanceof ApiError && e.code === "contact_required")) throw e;
        const methods = (e.detail as { methods?: string[] }).methods ?? [];
        setContact({ kind: methods[0] === "email" ? "email" : "phone", purpose });
      }
    });
  }

  // A way to pay (PAYMENT_METHODS): recorded on the bill; then «Оплатить» or the «Счёт на оплату» file.
  async function chooseWay(body: WayBody, then?: "claim" | "bill") {
    const invoice = c?.payment?.invoice_id;
    if (!invoice) return;
    await run(async () => {
      const out = await api<{ case: CaseView }>(`/v1/invoices/${invoice}/way`, { method: "POST", body: JSON.stringify(body) });
      setCase(out.case);
      if (then === "claim") {
        const claimed = await api<{ case: CaseView }>(`/v1/cases/${id}/payment/claim`, { method: "POST", body: "{}" });
        setCase(claimed.case);
        // the Kaspi Pay link is paid on trust (owner 01.10): the document is made at once, waiting on their return
        if (claimed.case.payment?.trusted && claimed.case.payment.status === "paid") {
          const next = await api<{ case: CaseView }>(`/v1/cases/${id}/actions/next`, { method: "POST", body: "{}" });
          setCase(next.case);
          setPayOpen(false);
        }
      }
      if (then === "bill") {
        const blob = await fetchFile(`/v1/invoices/${invoice}/bill?format=pdf`);
        saveBlob(blob, `schet-${invoice}.${blob.type.includes("pdf") ? "pdf" : "docx"}`);
      }
    });
  }

  // Contact confirmed: switch to the account token (it may be an existing account the case has just moved to), then
  // go on by itself: the bill for the chosen option, or the document at once if that account has a free one.
  async function contactConfirmed(r: SignedIn) {
    applySignIn(r);
    const purpose = contact?.purpose;
    setContact(null);
    const view = await api<CaseView>(`/v1/cases/${id}`).catch(() => null);
    if (view) setCase(view);
    if (view?.payment?.status === "paid") await post("/actions/next");
    else if (purpose) await choosePayment(purpose);
  }

  // The code could not be sent (the channel is down): the server stops asking for it, so go on to the bill (QA BUG-01)
  async function contactDown() {
    const purpose = contact?.purpose;
    setContact(null);
    if (purpose) await choosePayment(purpose);
  }

  // While the transfer is being checked, look every 2 s. The server makes the document the moment the payment is
  // confirmed, so it simply appears; if it has not after a few checks, the page asks for it itself.
  // from the chat's card «Оплатить» (?pay=1, P0 02.10): the payment window opens as soon as the case is ready for it
  const askedToPay = useRef(false);
  useEffect(() => {
    if (!c || askedToPay.current || typeof window === "undefined") return;
    if (new URLSearchParams(window.location.search).get("pay") !== "1") return;
    if (c.status !== "qualified" || c.payment?.status === "paid") return;
    askedToPay.current = true;
    setPayOpen(true);
    if (!c.payment?.code && c.payment?.status === "none") choosePayment("document");
  }, [c]);  // eslint-disable-line react-hooks/exhaustive-deps
  const payStatus = c?.payment?.status;
  const prepareRef = useRef(post);
  prepareRef.current = post;
  useEffect(() => {
    if (payStatus !== "awaiting_confirmation") return;
    let paidChecks = 0;
    const timer = setInterval(async () => {
      try {
        const view = await api<CaseView>(`/v1/cases/${id}`);
        const waiting = view.status === "qualified" || (view.status === "awaiting_response" && view.proposal?.type === "prepare_action");
        if (!waiting) { clearInterval(timer); setCase(view); setPayOpen(false); return; }  // the document is there
        if (view.payment?.status !== "paid") { setCase(view); return; }
        // paid, the document is being made: the window keeps "checking" until it is there
        if (++paidChecks >= 3) { clearInterval(timer); await prepareRef.current("/actions/next"); setPayOpen(false); }
      } catch { /* a missed check is retried on the next tick */ }
    }, 2000);
    return () => clearInterval(timer);
  }, [payStatus, id]);

  if (error && !c) return <div className="mx-auto max-w-2xl p-4"><Alert tone="danger" role="alert">{error}</Alert></div>;
  if (!c) return <p className="p-4 text-muted">{t("common.loading")}</p>;

  const last = c.actions.at(-1);
  const proposal = c.proposal;
  const q = c.question;
  const cov = c.coverage;
  const choosingForum = c.status === "intake" && !c.scenario && cov.options.length > 0;
  const ack = c.status === "intake" ? c.safety.pending_ack : null;
  const title = c.scenario?.title ?? cov.dispute?.title ?? t("case.untitled");
  const interviewing = c.status === "intake" && !choosingForum && !ack;

  const sections: MoreSection[] = [
    ...(c.roadmap ? [{ key: "roadmap", icon: "map" as IconName, label: t("app.roadmap"), render: () => <RoadmapView roadmap={c.roadmap!} /> }] : []),
    { key: "facts", icon: "document", label: t("app.facts"), render: () => <FactsPanel c={c} /> },
    ...(c.actions.length > 0 ? [{ key: "docs", icon: "save" as IconName, label: t("app.documents"),
      render: () => <>{c.actions.map((a) => <ActionCard key={a.id} caseId={c.id} a={a} onCase={setCase} />)}</> }] : []),
    ...(LAWYERS_PUBLIC || (LAWYER_PILOT && pilotOpen) ? [{ key: "lawyer", icon: "lawyer" as IconName, label: t("app.lawyer"), render: () => (
      <>
        {LAWYER_PILOT && <LawyerPilot caseId={c.id} onChange={setPilotStatus} />}
        <LawyerBlock key={pilotStatus ?? "none"} caseId={c.id} />
        {LAWYERS_PUBLIC && (
          <div className="card space-y-2 text-sm">
            <p className="text-muted">{t("cta.caseLawyerText")}</p>
            <Button href="/lawyers" variant="secondary" className="w-full" icon="lawyer">{t("cta.lawyer")}</Button>
          </div>
        )}
      </>) }] : []),
    ...(c.status !== "intake" ? [{ key: "gov", icon: "building" as IconName, label: t("app.gov"), render: () => <GovServices caseId={c.id} /> }] : []),
    ...(c.jurisdiction === "KZ" ? [{ key: "law", icon: "scroll" as IconName, label: t("app.law"), render: () => <LawQuestions caseId={c.id} /> }] : []),
    { key: "about", icon: "info", label: t("app.about"), render: () => (
      <>
        <div className="card space-y-3">
          <LevelBadge level={cov.level} />
          <LevelExplainer level={cov.level} />
          {cov.reasons.length > 0 && <ul className="flex flex-wrap gap-2">{cov.reasons.map((r) => <li key={r.code}><Badge tone="warning">{r.label}</Badge></li>)}</ul>}
          {cov.forum && <p className="flex items-center gap-2 text-sm"><Icon name="building" size={18} className="text-brand" />{cov.forum.name}</p>}
          <StageProgress stage={c.stage} />
        </div>
        {cov.upl_notice && <Alert tone="info" icon="info" title={t("case.uplTitle")}>{cov.upl_notice}</Alert>}
        <ReportsHint />
        <TrainingConsent c={c} onChange={setCase} />
        <div className="rounded-2xl border border-line p-4 text-xs text-muted">
          <p className="flex items-center gap-1.5 font-semibold text-ink"><Icon name="info" size={16} />{c.ai_label}</p>
          <p className="mt-1">{c.service_disclaimer}</p>
          <p className="mt-1">{t("legal.disclaimer")}</p>
        </div>
      </>) },
  ];
  const links: MoreLink[] = [
    { href: `/chat/${c.id}`, icon: "sparkle", label: t("chat.open") },
    { href: "/cases", icon: "briefcase", label: t("nav.cases") },
    { href: "/account", icon: "user", label: t("app.account") },
    { href: "/", icon: "home", label: t("app.home") },
    { href: `/support?case=${c.id}`, icon: "mail", label: t("footer.support") },
    { href: "/terms", icon: "scroll", label: t("legal.terms") },
  ];

  let bar: React.ReactNode = null;
  if (interviewing) {
    bar = <AnswerBar question={q && { ...q, optional: q.optional || SKIP_WORD.test(q.text) }} busy={busy} currency={c.currency} onSend={sendAnswer} onFiles={upload}
      onSkip={() => sendAnswer("пропустить")} onDone={() => sendAnswer("готово")} placeholder={t("case.morePlaceholder")} />;
  } else if (c.status !== "intake") {
    // owner 01.10 («3 клика»): one document by default — the bill is made at once; «Дело под ключ» is a link
    bar = (
      <>
        <NextStepBar c={c} busy={busy} post={post} run={run} setCase={setCase} openPay={(purpose?: string) => {
          setPayOpen(true);
          if (!c.payment?.code && c.payment?.status === "none") choosePayment(purpose ?? "document");
        }} />
        {LAWYER_PILOT && c.status !== "handed_to_lawyer" && (
          <button type="button" onClick={() => setChooseOpen(true)}
            className="mt-1 flex min-h-11 w-full items-center justify-center gap-2 rounded-full text-[15px] font-medium text-brand hover:bg-sand">
            <Icon name="lawyer" size={18} />{t("choose.button")}
          </button>
        )}
      </>
    );
  }

  return (
    <AppShell title={title} subtitle={c.status_label} sections={sections} links={links} bar={bar} wallpaper avatar tabs={false}
      scrollKey={`${log.length}-${busy}-${c.status}-${c.actions.length}-${c.payment?.code ?? ""}-${c.payment?.status ?? ""}`}>
      {c.scenario?.beta && <BetaNotice disclaimer={c.scenario.disclaimer} />}
      {c.scenario?.draft_disclaimer && (
        <p className="flex items-start gap-2 rounded-2xl bg-draft-50 px-3 py-2 text-xs text-draft">
          <Icon name="info" size={16} className="mt-0.5" /><span><b>{t("case.draftTitle")}.</b> {c.scenario.draft_disclaimer}</span>
        </p>
      )}
      {c.safety.hold_reason && <Alert tone="warning" title={t("case.holdTitle")}>{c.safety.hold_message}</Alert>}
      {emergency && <EmergencyPanel info={emergency} onContinue={() => setEmergency(null)} />}

      {c.plan && !choosingForum && (c.status === "intake" || c.status === "qualified") && (
        <PlanCard plan={c.plan} />
      )}

      <div className="space-y-2" aria-live="polite">
        {log.map((m, i) => (
          <Bubble key={i} mine={m.from === "user"}>
            <p className="whitespace-pre-line">{m.from === "bot" ? forScreen(m.text) : m.text}</p>
          </Bubble>
        ))}
        {busy && (
          <Bubble mine={false}>
            <span className="flex items-center gap-2 text-muted" role="status">
              {c.status === "intake" ? t("case.thinking") : t("case.working")}
              <span className="flex items-center gap-1" aria-hidden>
                {[0, 1, 2].map((k) => (
                  <span key={k} className="h-1.5 w-1.5 rounded-full bg-muted motion-safe:animate-bounce" style={{ animationDelay: `${k * 150}ms` }} />
                ))}
              </span>
            </span>
          </Bubble>
        )}
      </div>

      {/* PM 01.10: the draft first (part blurred, blanks to fill), then payment */}
      {c.status === "qualified" && (
        <DraftPreview caseId={c.id} version={`${c.facts.length}:${c.payment?.status ?? ""}`} onCase={setCase} />
      )}

      {chooseOpen && <ChooseLawyer caseId={c.id} onClose={() => setChooseOpen(false)} onChange={setPilotStatus} />}

      {payOpen && c.payment && c.payment.status !== "paid" && (c.status === "qualified" || proposal?.type === "prepare_action") && (
        <PaymentDialog pay={c.payment} busy={busy} onClose={() => setPayOpen(false)} contact={contact?.kind ?? null}
          applicant={applicant?.fields ?? null} caseId={c.id}
          onApplicant={async () => { const purpose = applicant?.purpose ?? "document"; setApplicant(null); await choosePayment(purpose); }}
          onContact={contactConfirmed} onContactDown={contactDown} onChoose={choosePayment} onClaim={() => post("/payment/claim")} onWay={chooseWay} />
      )}

      {ack && (
        <Alert tone={ack === "false_report" ? "warning" : "info"} title={t(`ack.${ack}.title`)}
          actions={<Button disabled={busy} onClick={() => acknowledge(ack)} icon="check">{t(`ack.${ack}.button`)}</Button>}>
          {log.at(-1)?.from === "bot" && log.at(-1)?.text ? log.at(-1)!.text : t(`ack.${ack}.text`)}
        </Alert>
      )}

      {choosingForum && <ForumChoice options={cov.options} busy={busy} onChoose={chooseForum} />}

      {c.status === "handed_to_lawyer" && (
        <Alert tone="info" icon="lawyer" title={t("case.lawyerTitle")}
          actions={LAWYERS_PUBLIC ? <Button href="/lawyers" variant="secondary" iconEnd="arrowRight">{t("case.lawyerCta")}</Button> : undefined}>
          {proposal?.message || log.find((m) => m.from === "bot")?.text || t("case.lawyerText")}
        </Alert>
      )}

      {c.status !== "intake" && last && <ActionCard caseId={c.id} a={last} onCase={setCase} />}

      {c.status === "awaiting_response" && proposal?.message && (
        <Bubble mine={false}><p className="whitespace-pre-line">{proposal.message}</p></Bubble>
      )}

      {c.outcome && (
        <div className="card text-sm">
          <p className="font-semibold">{t("case.outcome")}: {c.outcome.result}</p>
          {c.outcome.amount_recovered && <p>{c.outcome.amount_recovered} {c.outcome.currency}</p>}
          <p className="text-muted">{c.outcome.days_to_resolution} {t("case.days")}</p>
        </div>
      )}
      {/* the document is ready or the case is closed: the moment to pass the service on (both get a free document) */}
      {(c.outcome || (c.status !== "intake" && (last?.downloadable || c.payment?.status === "paid"))) && <Invite big />}
      {error && <Alert tone="danger" role="alert">{error}</Alert>}
    </AppShell>
  );
}

function FactsPanel({ c }: { c: CaseView }) {
  const t = useT();
  if (c.facts.length === 0 && c.evidence.length === 0) return <p className="text-sm text-muted">{t("app.noFacts")}</p>;
  return (
    <div className="space-y-3">
      <dl className="divide-y divide-line rounded-2xl border border-line">
        {c.facts.map((f) => (
          <div key={f.field} className="px-4 py-2.5">
            <dt className="text-xs text-muted">{f.label}</dt>
            <dd className="break-words">{f.value}</dd>
          </div>
        ))}
      </dl>
      {c.evidence.length > 0 && (
        <ul className="space-y-1 text-sm">
          {c.evidence.map((e) => <li key={e.id} className="flex items-center gap-2"><Icon name="paperclip" size={16} className="text-brand" />{e.filename}</li>)}
        </ul>
      )}
    </div>
  );
}

/** What to do now once the document stage has started: submitted? got a reply? close the case. */
function NextStepBar({ c, busy, post, openPay, run, setCase }: {
  c: CaseView; busy: boolean; post: (path: string, body?: unknown) => Promise<void>; openPay: (purpose?: string) => void;
  run: (fn: () => Promise<void>) => Promise<boolean>; setCase: (c: CaseView) => void;
}) {
  const t = useT();
  const [responseText, setResponseText] = useState("");
  const [showResponse, setShowResponse] = useState(false);
  const [amount, setAmount] = useState("");
  const last = c.actions.at(-1);
  const proposal = c.proposal;
  const big = "min-h-12 flex-1";

  // Not paid yet: the button opens the payment window (the document is then prepared by itself once paid).
  const pay = c.payment;
  const needsPay = !!pay && pay.status !== "paid" && !c.safety.hold_reason;
  const prepareOrPay = (label: string, icon: IconName = "document") => (
    needsPay && !pay!.available
      ? <p className="flex items-center gap-2 py-2 text-sm"><Icon name="alert" size={18} className="text-warning" />{t("payment.unavailable")}</p>
      : <Button className="min-h-12 w-full" disabled={busy} icon={needsPay && pay!.status === "awaiting_confirmation" ? "hourglass" : icon}
          onClick={() => (needsPay ? openPay() : post("/actions/next"))}>
          {needsPay && pay!.status === "awaiting_confirmation" ? t("payment.checking") : label}
        </Button>
  );

  if (c.status === "qualified") {
    const whole = pay?.options.find((o) => o.purpose === "case");
    return (
      <div className="space-y-1">
        {prepareOrPay(t("case.prepare"))}
        {needsPay && pay!.available && pay!.status === "none" && whole && (
          <button type="button" disabled={busy} onClick={() => openPay("case")}
            className="flex min-h-11 w-full items-center justify-center text-center text-sm text-muted underline">
            {t("payment.option.case", { price: money(whole.amount, pay!.currency) })}
          </button>
        )}
      </div>
    );
  }
  if (c.status === "action_ready" && last) {
    if (last.approval_status === "pending" || last.approval_status === "rejected") {
      return <p className="flex items-center gap-2 py-2 text-sm"><Icon name="lawyer" size={18} className="text-brand" />
        {last.approval_status === "pending" ? t("case.awaitingApproval") : t("case.rejected")}</p>;
    }
    return (
      <div className="space-y-2">
      <p className="px-1 text-xs text-muted">{t("case.submittedHint")}</p>
      <div className="flex gap-2">
        {/* sending itself (WhatsApp, Telegram, e-mail through us…) is the «Мастер отправки» in the document card */}
        <Button className={big} disabled={busy} icon="check" onClick={() => post(`/actions/${last.id}/submitted`, { via: "user_submits" })}>{t("case.submitted")}</Button>
      </div>
      </div>
    );
  }
  if (c.status === "awaiting_response" && last && proposal) {
    if (proposal.type === "wait" && !showResponse) {
      return (
        <div className="flex gap-2">
          <Button className={big} icon="mail" onClick={() => setShowResponse(true)}>{t("case.gotResponse")}</Button>
          <Button className={big} variant="secondary" disabled={busy} icon="hourglass"
            onClick={() => post(`/actions/${last.id}/response`, { no_response: true })}>{t("case.noResponse")}</Button>
        </div>
      );
    }
    if (proposal.type === "wait") {
      return (
        <div className="space-y-2">
          <label htmlFor="resp" className="sr-only">{t("case.responsePlaceholder")}</label>
          <textarea id="resp" className="input" rows={3} placeholder={t("case.responsePlaceholder")}
            value={responseText} onChange={(e) => setResponseText(e.target.value)} />
          <div className="flex flex-wrap items-center gap-2">
            <Button disabled={busy || !responseText.trim()}
              onClick={() => post(`/actions/${last.id}/response`, { text: responseText }).then(() => setShowResponse(false))}>{t("case.responseSend")}</Button>
            <FilePicker attachLabel={t("case.responseFile")} disabled={busy} onFile={(f) => {
              run(async () => {
                const form = new FormData();
                form.append("file", f);
                const out = await api<{ case: CaseView }>(`/v1/cases/${c.id}/actions/${last.id}/response/file`, { method: "POST", body: form });
                setCase(out.case);
                setShowResponse(false);
              });
            }} />
            <button type="button" className="px-2 text-sm text-muted" onClick={() => setShowResponse(false)}>{t("app.cancel")}</button>
          </div>
        </div>
      );
    }
    if (proposal.type === "clarify") {
      return (
        <div className="grid grid-cols-2 gap-2">
          {(["full", "partial", "refusal", "none"] as const).map((cls) => (
            <Button key={cls} variant="secondary" disabled={busy} className="min-h-12"
              onClick={() => post(`/actions/${last.id}/response`, { response_class: cls })}>{t(`case.classes.${cls}`)}</Button>
          ))}
        </div>
      );
    }
    return (
      <div className="space-y-2">
        {proposal.type === "prepare_action" && prepareOrPay(proposal.title ?? t("case.prepare"))}
        {proposal.type === "handoff" && (
          <Button className="min-h-12 w-full" disabled={busy} icon={proposal.type === "handoff" ? "lawyer" : "document"} onClick={() => post("/actions/next")}>
            {proposal.type === "handoff" ? t("case.handoff") : proposal.title}
          </Button>
        )}
        <details className="rounded-2xl border border-line px-3 py-2">
          <summary className="cursor-pointer text-sm font-semibold">{t("case.close")}</summary>
          <div className="space-y-2 pt-2">
            <label htmlFor="amount" className="sr-only">{t("case.amountRecovered")}</label>
            <input id="amount" className="input" inputMode="numeric"
              placeholder={`${t("case.amountRecovered")}, ${c.currency ?? ""}`} value={amount} onChange={(e) => setAmount(e.target.value.replace(/[^\d]/g, ""))} />
            <div className="grid grid-cols-3 gap-2">
              {(["won", "partial", "lost"] as const).map((r) => (
                <Button key={r} variant={r === proposal.suggested_result ? "primary" : "secondary"} disabled={busy}
                  onClick={() => post("/close", { result: r, amount_recovered: amount || (r === "won" ? c.amount_at_stake : null) })}>
                  {t(`case.close${r[0].toUpperCase()}${r.slice(1)}`)}
                </Button>
              ))}
            </div>
          </div>
        </details>
      </div>
    );
  }
  return null;
}

function money(amount: number, currency: string | null): string {
  return `${amount.toLocaleString("ru-RU").replace(/\u00a0/g, " ")} ${currency === "KZT" ? "₸" : currency ?? ""}`.trim();
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

/** Payment window, opened by «Подготовить документ» while the document is not paid: choose one document or
 *  «Дело под ключ», confirm a phone by SMS code if the server asks (an e-mail where SMS is not available), Kaspi
 *  details and the code, "I have paid". Once the transfer is confirmed the page prepares the
 *  document by itself (and the server does, if the page is closed). */
type ApplicantField = { field: string; label: string; type: string; pattern: string | null };

/** The applicant's own data for the document, asked on one screen right before paying (PM 01.10). */
function ApplicantForm({ caseId, fields, onDone }: { caseId: string; fields: ApplicantField[]; onDone: () => void }) {
  const t = useT();
  const [values, setValues] = useState<Record<string, string>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setErrors({});
    try {
      await api(`/v1/cases/${caseId}/facts`, { method: "POST", body: JSON.stringify({ values }) });
      onDone();
    } catch (err) {
      const f = err instanceof ApiError ? (err.detail as { fields?: Record<string, string> })?.fields : undefined;
      setErrors(f ?? { _: "generic" });
    } finally { setBusy(false); }
  }
  const known = ["pattern", "address", "date", "date_future", "money", "email", "phone"];
  return (
    <form onSubmit={save} className="space-y-3">
      <p className="text-base font-semibold">{t("payment.applicant.title")}</p>
      <p className="text-sm text-muted">{t("payment.applicant.lead")}</p>
      {fields.map((f) => (
        <label key={f.field} className="block text-sm">{f.label}
          <input className={`input mt-1 ${errors[f.field] ? "border-danger" : ""}`} required value={values[f.field] ?? ""}
            type={f.type === "phone" ? "tel" : f.type === "email" ? "email" : "text"}
            inputMode={f.type === "phone" ? "tel" : f.pattern ? "numeric" : undefined}
            autoComplete={f.type === "phone" ? "tel" : f.field.endsWith("name") ? "name" : f.field.endsWith("address") ? "street-address" : undefined}
            onChange={(e) => setValues((v) => ({ ...v, [f.field]: e.target.value }))} aria-invalid={!!errors[f.field]} />
          {errors[f.field] && <span className="text-danger">{t(`draft.error.${known.includes(errors[f.field]) ? errors[f.field] : "generic"}`)}</span>}
        </label>
      ))}
      {errors._ && <p role="alert" className="text-danger">{t("draft.error.generic")}</p>}
      <Button type="submit" className="min-h-12 w-full" disabled={busy}>{t("payment.applicant.continue")}</Button>
    </form>
  );
}

function PaymentDialog({ pay, busy, contact, applicant, caseId, onApplicant, onClose, onContact, onContactDown, onChoose, onClaim, onWay }: {
  pay: Payment; busy: boolean; contact: "phone" | "email" | null; onClose: () => void; onContact: (r: SignedIn) => void;
  applicant: ApplicantField[] | null; caseId: string; onApplicant: () => void;
  onContactDown: () => void;
  onChoose: (purpose: string) => void; onClaim: () => void; onWay: (body: WayBody, then?: "claim" | "bill") => void;
}) {
  const t = useT();
  const panel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", esc);
    panel.current?.focus();
    return () => document.removeEventListener("keydown", esc);
  }, [onClose]);
  const waiting = pay.status === "awaiting_confirmation";
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center" role="dialog" aria-modal="true" aria-labelledby="pay-title">
      <button type="button" aria-label={t("app.close")} onClick={onClose} className="absolute inset-0 bg-ink/40" />
      <div ref={panel} tabIndex={-1}
        className="relative flex max-h-[92dvh] w-full max-w-lg flex-col rounded-t-3xl bg-surface pb-[env(safe-area-inset-bottom)] shadow-[var(--shadow-raised)] outline-none sm:rounded-3xl">
        <div className="flex items-center gap-2 border-b border-line py-2 ps-4 pe-2">
          <Icon name="coin" className="text-brand" />
          <h2 id="pay-title" className="flex-1 truncate text-lg font-semibold">{t(pay.purpose === "case" && pay.code ? "payment.titleCase" : "payment.title")}</h2>
          <button type="button" onClick={onClose} aria-label={t("app.close")}
            className="flex h-11 w-11 items-center justify-center rounded-full hover:bg-sand"><Icon name="x" size={22} /></button>
        </div>
        <div className="space-y-3 overflow-y-auto overscroll-contain p-4">
          {!pay.code && applicant && applicant.length > 0 ? (
            <ApplicantForm caseId={caseId} fields={applicant} onDone={onApplicant} />
          ) : !pay.code && contact ? (
            <>
              <p className="flex items-start gap-2 text-base font-semibold">
                <Icon name={contact === "phone" ? "phone" : "mail"} className="mt-0.5 shrink-0 text-brand" />{t(`payment.contact.${contact}`)}
              </p>
              <p className="text-sm text-muted">{t("payment.contact.lead")}</p>
              <CodeForm key={contact} kind={contact} onDone={onContact} onSendFailed={onContactDown} wide />
            </>
          ) : !pay.code ? (
            <>
              <p className="text-sm text-muted">{t("payment.choose")}</p>
              {pay.options.map((o) => (
                <Button key={o.purpose} className="min-h-12 w-full" variant={o.purpose === "case" ? "secondary" : undefined}
                  disabled={busy} icon={o.purpose === "case" ? "shieldCheck" : "document"} onClick={() => onChoose(o.purpose)}>
                  {t(`payment.option.${o.purpose}`, { price: money(o.amount, pay.currency) })}
                </Button>
              ))}
              <p className="text-xs text-muted">{t("payment.caseHint")}</p>
            </>
          ) : kaspiOneTap(pay) ? (
            <>
              {pay.owed && <Alert tone="warning" role="status">{t("payment.owed")}</Alert>}
              <KaspiOneTap pay={pay} busy={busy} price={money(pay.amount, pay.currency)} onWay={onWay} />
            </>
          ) : (
            <>
              {waiting && <Alert tone="info" icon="hourglass" role="status">{t("payment.waiting")}</Alert>}
              {pay.status === "not_found" && <Alert tone="warning" role="status">{t("payment.notFound")}</Alert>}
              <p className="text-2xl font-semibold tabular-nums">{money(pay.amount, pay.currency)}</p>
              {pay.ways?.length ? (
                <PaymentWays pay={pay} busy={busy} amount={String(pay.amount)} onWay={onWay}
                  copy={(label, value, mono) => <CopyValue label={label} value={value} mono={mono} />}
                  transfer={(
                    <>
                      <div className="space-y-2">
                        {pay.recipient_name && <CopyValue label={t("payment.recipient")} value={pay.recipient_name} />}
                        {pay.kaspi_phone && <CopyValue label={t("payment.kaspi")} value={pay.kaspi_phone} />}
                        <CopyValue label={t("payment.code")} value={pay.code} mono />
                      </div>
                      <p className="text-sm">{t("payment.steps")}</p>
                    </>
                  )} />
              ) : (
                <>
                  <div className="space-y-2">
                    {pay.recipient_name && <CopyValue label={t("payment.recipient")} value={pay.recipient_name} />}
                    {pay.kaspi_phone && <CopyValue label={t("payment.kaspi")} value={pay.kaspi_phone} />}
                    <CopyValue label={t("payment.code")} value={pay.code} mono />
                  </div>
                  <p className="text-sm">{t("payment.steps")}</p>
                </>
              )}
              {waiting ? (
                <Button className="min-h-12 w-full" variant="secondary" onClick={onClose}>{t("app.close")}</Button>
              ) : !pay.ways?.length && (
                <Button className="min-h-12 w-full" disabled={busy} icon="check" onClick={onClaim}>{t("payment.paid")}</Button>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

/** The proposed solution right after the story: document → addressee → how to file → what to attach. */
/** What will be made and what to attach — once, as Konsiliér's message; files are added from the box below. */
function PlanCard({ plan }: { plan: Plan }) {
  const t = useT();
  const portalName = (url: string | null) => (url ? url.replace(/^https?:\/\//, "").replace(/\/$/, "") : "");
  return (
    <Bubble mine={false}>
      <p className="font-semibold">{t("helper.planTitle")}</p>
      <p className="flex items-start gap-2"><Icon name="document" size={20} className="mt-0.5 shrink-0 text-[var(--chat-accent)]" />{plan.document}</p>
      {plan.addressee && (
        <p className="flex items-start gap-2 text-[16px]"><Icon name="building" size={18} className="mt-0.5 shrink-0 text-muted" />{plan.addressee}</p>
      )}
      {plan.channels.length > 0 && (
        <p className="flex flex-wrap gap-1.5 text-[15px]">
          {plan.channels.map((ch, i) => ch.url ? (
            <a key={i} href={ch.url} target="_blank" rel="noreferrer" className="rounded-full bg-surface px-2.5 py-0.5 hover:text-brand">
              {ch.kind === "portal" ? portalName(ch.url) : t(`forum.channel.${ch.kind}`)}
            </a>
          ) : <span key={i} className="rounded-full bg-surface px-2.5 py-0.5">{t(`forum.channel.${ch.kind}`)}</span>)}
        </p>
      )}
      {plan.attachments.length > 0 && (
        <>
          <p className="pt-1 text-[16px] font-semibold">{t("helper.planAttach")}</p>
          <ul className="space-y-1 text-[16px]">
            {plan.attachments.map((a) => (
              <li key={a} className="flex gap-2"><Icon name="checkCircle" size={18} className="mt-1 shrink-0 text-[var(--chat-accent)]" /><span>{a}</span></li>
            ))}
          </ul>
        </>
      )}
    </Bubble>
  );
}

type MenuItem = { key: string; label: string; icon?: IconName; run: () => Promise<unknown> };

/** Ready document: download (PDF / Word), print, save (PDF / Word, where you choose), send (WhatsApp, Telegram,
 *  e-mail, another app) and sign with ЭЦП. */
function DocumentToolbar({ caseId, a }: { caseId: string; a: CaseAction }) {
  const t = useT();
  const [busy, setBusy] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [signOpen, setSignOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const pdf = `/v1/cases/${caseId}/actions/${a.id}/document?format=pdf`;
  const docx = `/v1/cases/${caseId}/actions/${a.id}/document?format=docx`;
  const main = a.has_pdf ? { path: pdf, name: `${a.action_id}.pdf` } : { path: docx, name: `${a.action_id}.docx` };
  const signed = (a.signatures ?? []).length > 0;

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(null); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(null); };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", esc); };
  }, [open]);

  async function act(key: string, fn: () => Promise<unknown>) {
    setOpen(null); setBusy(key); setErr(null); setNote(null);
    try { await fn(); } catch (e) { setErr(errorText(e)); } finally { setBusy(null); }
  }

  // A file cannot be attached through a link: on phones the share sheet carries it to the chosen app;
  // elsewhere the file is downloaded and the app opens with a prepared message to attach it to.
  const sendTo = (app: "whatsapp" | "telegram" | "mail") => async () => {
    const text = `${a.title}${a.addressee?.name ? ` — ${a.addressee.name}` : ""}`;
    const coarse = matchMedia("(pointer: coarse)").matches;
    if (coarse && await shareFile(main.path, main.name, text)) return;
    if (!coarse) await downloadFile(main.path, main.name);
    const url = app === "whatsapp" ? `https://wa.me/?text=${encodeURIComponent(text)}`
      : app === "telegram" ? `https://t.me/share/url?url=${encodeURIComponent("https://konsilier.com")}&text=${encodeURIComponent(text)}`
      : `mailto:${a.addressee?.email ?? ""}?subject=${encodeURIComponent(a.title)}&body=${encodeURIComponent(text)}`;
    window.open(url, "_blank", "noopener");
    setNote(t("helper.doc_fileReady"));
  };

  const formats = (run: (path: string, name: string) => Promise<unknown>): MenuItem[] => [
    ...(a.has_pdf ? [{ key: "pdf", label: t("helper.doc_fmtPdf"), icon: "document" as IconName, run: () => run(pdf, `${a.action_id}.pdf`) }] : []),
    { key: "docx", label: t("helper.doc_fmtWord"), icon: "document", run: () => run(docx, `${a.action_id}.docx`) },
  ];
  const tools: { key: string; icon: IconName; label: string; menu?: MenuItem[]; run?: () => Promise<unknown>; active?: boolean }[] = [
    { key: "download", icon: "download", label: t("helper.doc_download"), menu: formats(downloadFile) },
    ...(a.has_pdf ? [{ key: "print", icon: "printer" as IconName, label: t("helper.doc_print"), run: () => printFile(pdf) }] : []),
    { key: "save", icon: "save", label: t("helper.doc_save"), menu: formats(saveFileAs) },
    { key: "send", icon: "share", label: t("helper.doc_send"), menu: [
      { key: "whatsapp", label: t("helper.doc_toWhatsapp"), icon: "send", run: sendTo("whatsapp") },
      { key: "telegram", label: t("helper.doc_toTelegram"), icon: "send", run: sendTo("telegram") },
      { key: "mail", label: t("helper.doc_toMail"), icon: "mail", run: sendTo("mail") },
      { key: "other", label: t("helper.doc_toOther"), icon: "share", run: () => shareFile(main.path, main.name, a.title) },
    ] },
    { key: "sign", icon: signed ? "shieldCheck" : "key", label: signed ? t("helper.doc_signed") : t("helper.doc_sign"),
      run: async () => setSignOpen((x) => !x), active: signOpen || signed },
  ];

  return (
    <div className="space-y-2" ref={ref}>
      <div className="grid grid-cols-3 gap-2 sm:grid-cols-5" role="toolbar" aria-label={a.title}>
        {tools.map((x) => (
          <div key={x.key} className="relative">
            <button type="button" disabled={busy !== null} aria-haspopup={x.menu ? "menu" : undefined}
              aria-expanded={x.menu ? open === x.key : undefined}
              onClick={() => (x.menu ? setOpen(open === x.key ? null : x.key) : act(x.key, x.run!))}
              className={`flex min-h-16 w-full flex-col items-center justify-center gap-1 rounded-2xl border p-2 text-xs font-medium hover:border-brand hover:text-brand disabled:opacity-50 ${x.active ? "border-brand bg-brand-50 text-brand" : "border-line bg-surface"}`}>
              <Icon name={busy === x.key ? "spinner" : x.icon} size={22} />
              <span className="flex items-center gap-0.5">{x.label}{x.menu && <Icon name="chevronDown" size={12} />}</span>
            </button>
            {x.menu && open === x.key && (
              <ul role="menu" className="absolute start-0 top-full z-20 mt-1 min-w-52 space-y-0.5 rounded-2xl border border-line bg-surface p-1 shadow-[var(--shadow-raised)]">
                {x.menu.map((m) => (
                  <li key={m.key} role="none">
                    <button type="button" role="menuitem" onClick={() => act(x.key, m.run)}
                      className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-start text-sm hover:bg-brand-50 hover:text-brand">
                      {m.icon && <Icon name={m.icon} size={16} />}{m.label}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        ))}
      </div>
      {note && <p className="text-xs text-muted" aria-live="polite">{note}</p>}
      {err && <p role="alert" className="text-xs text-danger">{err}</p>}
      {(signOpen || signed) && (
        <SignDocument base={`/v1/cases/${caseId}/actions/${a.id}`} fileBase={a.action_id} initial={a.signatures ?? []}
          unavailable={t("helper.doc_signUnavailable")} />
      )}
    </div>
  );
}

function ForumChoice({ options, busy, onChoose }: { options: ForumOption[]; busy: boolean; onChoose: (f: ForumOption) => void }) {
  const t = useT();
  return (
    <section className="space-y-3" aria-labelledby="forum-choice">
      <h2 id="forum-choice" className="text-lg font-semibold">{t("forum.chooseTitle")}</h2>
      <p className="text-sm text-muted">{t("forum.chooseLead")}</p>
      <ul className="grid gap-3 md:grid-cols-2">
        {options.map((f) => (
          <li key={f.id} className="card flex flex-col gap-3">
            <div className="flex items-start gap-3">
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand">
                <Icon name={f.type === "court" ? "landmark" : f.type === "mediation" ? "handshake" : "building"} />
              </span>
              <div className="min-w-0 space-y-1">
                <p className="font-semibold leading-snug">{f.name}</p>
                <p className="text-xs text-muted">{t(`forum.type.${f.type}`)}</p>
              </div>
            </div>
            <div className="flex flex-wrap gap-1.5">
              <Badge tone={f.legal_effect === "binding" ? "brand" : f.legal_effect === "advisory" ? "info" : "warning"}>
                {t(`forum.effect.${f.legal_effect}`)}
              </Badge>
              <Badge tone={f.verified ? "brand" : "neutral"} icon={f.verified ? "shieldCheck" : "hourglass"}>
                {f.verified ? t("forum.verified") : t("forum.unverified")}
              </Badge>
              {!f.deadline_known && <Badge>{t("forum.deadlineByLawyer")}</Badge>}
            </div>
            <p className="text-xs text-muted">{t("forum.channels")}: {f.channels.map((ch) => t(`forum.channel.${ch}`)).join(", ")}</p>
            <Button className="mt-auto" disabled={busy} onClick={() => onChoose(f)} iconEnd="arrowRight">{t("forum.choose")}</Button>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** Opt-in: the case, anonymised, may teach Konsiliér's own model. Off by default; can be withdrawn any time. */
function TrainingConsent({ c, onChange }: { c: CaseView; onChange: (c: CaseView) => void }) {
  const t = useT();
  const [busy, setBusy] = useState(false);
  const toggle = async (given: boolean) => {
    setBusy(true);
    try {
      onChange((await api<{ case: CaseView }>(`/v1/cases/${c.id}/training-consent`, {
        method: "PUT", body: JSON.stringify({ given }) })).case);
    } catch { /* the switch stays as it was */ } finally { setBusy(false); }
  };
  return (
    <label className="card flex cursor-pointer items-start gap-3 text-sm">
      <input type="checkbox" className="mt-1 h-5 w-5 shrink-0 accent-brand" checked={c.training_consent}
        disabled={busy} onChange={(e) => toggle(e.target.checked)} />
      <span className="space-y-1">
        <span className="block font-semibold text-ink">{t("training.title")}</span>
        <span className="block text-muted">{t("training.text")}</span>
      </span>
    </label>
  );
}

function ReportsHint() {
  const t = useT();
  const [show, setShow] = useState(false);
  useEffect(() => {
    api<Me>("/v1/me").then((m) => setShow(!m.identities.some((i) => i.kind === "email"))).catch(() => setShow(false));
  }, []);
  if (!show) return null;
  return (
    <div className="card flex flex-wrap items-center gap-3 text-sm">
      <Icon name="mail" className="text-brand" />
      <span className="flex-1">{t("reports.hint")}</span>
      <Link href="/account" className="btn-ghost">{t("reports.hintCta")}</Link>
    </div>
  );
}

function LawyerBlock({ caseId }: { caseId: string }) {
  const t = useT();
  const [data, setData] = useState<CaseLawyer | null>(null);
  useEffect(() => {
    api<CaseLawyer>(`/v1/cases/${caseId}/lawyer`).then(setData).catch(() => setData(null));
  }, [caseId]);
  if (!data?.lawyer) return null;
  return (
    <section aria-labelledby="your-lawyer" className="space-y-3">
      <div className="card flex items-center gap-3">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand"><Icon name="lawyer" /></span>
        <div>
          <h2 id="your-lawyer" className="font-semibold">{t("agreements.yourLawyer")}: {data.lawyer.name}</h2>
          <p className="text-sm text-muted">{t(`agreements.kind.${data.lawyer.kind}`)}{data.lawyer.organization ? ` · ${data.lawyer.organization}` : ""}</p>
        </div>
      </div>
      <Agreements items={data.agreements} role="applicant" />
    </section>
  );
}

function ActionCard({ caseId, a, onCase }: { caseId: string; a: CaseAction; onCase?: (c: CaseView) => void }) {
  const t = useT();
  const { lang } = useLang();
  if (a.kind === "handoff") {
    return <div className="card flex items-center gap-2 text-sm"><Icon name="lawyer" className="text-brand" />{a.title}</div>;
  }
  const notSubmitted = !a.submitted_at && !["submitted", "responded"].includes(a.status);
  const wizard = a.downloadable && !!a.email_send && a.email_send.reason !== "payment_required"
    && ["ready", "submitted"].includes(a.status);
  return (
    <div className="card space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-semibold">{a.sequence}. {a.title}</h3>
        {a.paid && !a.response_label && <Badge tone="brand" icon="checkCircle">{t("case.paid")}</Badge>}
        {a.response_label && <Badge>{t("case.response")}: {a.response_label}</Badge>}
      </div>
      {a.downloadable && a.filing
        ? <FilingCard id={a.id} f={a.filing} />
        : a.addressee?.name && <p className="flex items-center gap-1.5 text-sm text-muted"><Icon name="building" size={16} />{a.addressee.name}</p>}
      {a.downloadable && <DocumentToolbar caseId={caseId} a={a} />}
      {/* One sending block: the wizard plans the route (e-mail, a messenger, or the appeal portal for a state body
          — its step opens the portal bridge inside the wizard). Without the wizard (a free document) the portal
          bridge stands alone; the registered appeal is shown with its number and date. */}
      {wizard && <SendWizard caseId={caseId} a={a} onCase={onCase} />}
      {a.downloadable && !wizard && a.appeal_portal && !a.filed && notSubmitted && <EotinishBridge caseId={caseId} a={a} onCase={onCase} />}
      {a.filed && <EotinishFiled caseId={caseId} a={a} onCase={onCase} />}
      {a.downloadable && !a.appeal_portal && notSubmitted && <SubmitOnline caseId={caseId} a={a} />}
      {a.downloadable && a.instructions.length > 0 && (
        <div className="space-y-2">
          <p className="text-sm font-semibold">{a.filing ? t("filing.stepByStep") : t("case.instructions")}</p>
          <ol className="space-y-2 text-sm">
            {a.instructions.map((s, i) => (
              <li key={i} className="flex gap-3">
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-50 text-xs font-semibold text-brand">{i + 1}</span>
                <span className="min-w-0 break-words pt-0.5"><Step text={s} /></span>
              </li>
            ))}
          </ol>
        </div>
      )}
      {a.deadline && (
        <p className="flex flex-wrap items-center gap-2 text-sm">
          <Icon name="clock" size={18} className="text-brand" />
          {t("case.deadline")}: <b className="tabular-nums">{new Date(a.deadline.due_date).toLocaleDateString(lang === "ar" ? "ar" : "ru-RU")}</b>
          <Badge>{t(`case.deadlineStatus.${a.deadline.status}`)}</Badge>
        </p>
      )}
      {a.response_summary && <p className="text-sm text-muted">«{a.response_summary}»</p>}
    </div>
  );
}

/** «Как подать»: where, until when, how long they have to answer and which ways — compact, phone first.
 *  Anything the pack data does not hold is shown as «уточнит юрист», never guessed. */
function FilingCard({ id, f }: { id: string; f: Filing }) {
  const t = useT();
  const { lang } = useLang();
  const online = f.online && (f.online.phone || f.online.desktop) ? f.online : null;
  const [tab, setTab] = useState<"phone" | "desktop">(online && (!online.phone_ok || !online.phone) ? "desktop" : "phone");
  const lawyer = <span className="text-muted">{t("filing.lawyer")}</span>;
  const within = (d: { days: number; unit: string }) => {
    let form = "other";
    try { form = new Intl.PluralRules(lang).select(d.days) === "one" ? "one" : "other"; } catch {}
    return t(`filing.within.${d.unit}.${form}`, { n: d.days });
  };
  const date = (iso: string) => new Date(iso).toLocaleDateString(lang === "ar" ? "ar" : "ru-RU");
  const norm = (d: { norm_ref: string | null; verified: boolean }) => (
    <span className="block text-xs text-muted">{d.norm_ref && d.verified ? t("filing.norm", { ref: d.norm_ref }) : <>{t("filing.norm", { ref: "" }).trim()} {t("filing.lawyer")}</>}</span>
  );
  const row = (icon: IconName, label: string, body: ReactNode) => (
    <div className="flex gap-3">
      <Icon name={icon} size={18} className="mt-0.5 shrink-0 text-brand" />
      <div className="min-w-0 flex-1">
        <dt className="text-xs text-muted">{label}</dt>
        <dd className="break-words text-sm text-ink">{body}</dd>
      </div>
    </div>
  );
  const steps = online ? online[tab] : null;
  return (
    <section className="space-y-3 rounded-2xl border border-line bg-surface p-4" aria-labelledby={`filing-${id}`}>
      <h4 id={`filing-${id}`} className="flex items-center gap-2 font-semibold text-ink"><Icon name="send" size={18} />{t("filing.title")}</h4>
      <dl className="space-y-3">
        {row("building", t("filing.to"), (
          <>
            {f.to.name ? <span className="block font-medium">{f.to.name}</span> : lawyer}
            {f.to.address && <span className="block text-muted">{f.to.address}</span>}
            {f.to.email && <a href={`mailto:${f.to.email}`} className="link block">{f.to.email}</a>}
          </>
        ))}
        {f.file_by && row("calendar", t("filing.fileBy"), (
          <>
            {f.file_by.date
              ? <b className="tabular-nums">{date(f.file_by.date)}</b>
              : <span>{within(f.file_by)}{f.file_by.since ? ` ${f.file_by.since}` : ""}</span>}
            {f.file_by.date && <span className="block text-xs text-muted">{within(f.file_by)}{f.file_by.since ? ` ${f.file_by.since}` : ""}</span>}
            {norm(f.file_by)}
            {f.file_by.overdue && <span className="block text-xs text-danger">{t("filing.overdue")}</span>}
          </>
        ))}
        {f.response && row("clock", t("case.deadline"), (
          <>
            <span>{t("filing.respond", { term: within(f.response) })}</span>
            {norm(f.response)}
          </>
        ))}
        {f.signature_text && row("key", t("filing.signature"), f.signature_text)}
      </dl>
      {f.ways.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs text-muted">{t("filing.ways")}</p>
          <ul className="grid gap-2 sm:grid-cols-2">
            {f.ways.map((w) => (
              <li key={w.kind} className="rounded-xl bg-sand px-3 py-2">
                <span className="text-sm font-semibold text-ink">{w.label}</span>
                <span className="block text-xs text-muted">{w.hint}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {online && (
        <div className="space-y-3">
          <div role="tablist" aria-label={t("filing.title")} className="grid grid-cols-2 gap-1 rounded-xl bg-sand p-1">
            {(["phone", "desktop"] as const).map((k) => (
              <button key={k} type="button" role="tab" id={`filing-${id}-${k}`} aria-selected={tab === k}
                aria-controls={`filing-${id}-panel`} onClick={() => setTab(k)}
                className={`flex min-h-10 items-center justify-center gap-1.5 rounded-lg text-sm font-semibold ${tab === k ? "bg-surface text-ink shadow-sm" : "text-muted"}`}>
                <Icon name={k === "phone" ? "smartphone" : "key"} size={16} />{t(`filing.${k}`)}
              </button>
            ))}
          </div>
          <div role="tabpanel" id={`filing-${id}-panel`} aria-labelledby={`filing-${id}-${tab}`} className="space-y-3">
            {steps ? (
              <ol className="space-y-2 text-sm">
                {steps.map((s, i) => (
                  <li key={i} className="flex gap-3">
                    <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-50 text-xs font-semibold text-brand">{i + 1}</span>
                    <span className="min-w-0 break-words pt-0.5"><Step text={s} /></span>
                  </li>
                ))}
              </ol>
            ) : <p className="text-sm">{lawyer}</p>}
            <a href={online.url} target="_blank" rel="noreferrer" className="btn-ghost min-h-11 w-full sm:w-auto">
              {t("filing.open", { portal: online.portal })}<Icon name="external" size={16} />
            </a>
          </div>
        </div>
      )}
    </section>
  );
}

type Portal = { key: "eotinish" | "court" | "site"; name: string; url: string };

/** Where this document is filed online: eOtinish for state bodies, the Judicial Cabinet for courts, or the
 *  addressee's own filing page. Null when the document goes by e-mail or on paper. */
function portalOf(a: CaseAction): Portal | null {
  const url = a.addressee?.submit_url ?? "";
  if (/eotinish\.kz/.test(url)) return { key: "eotinish", name: "eOtinish", url: "https://eotinish.kz" };
  if (a.addressee?.kind === "court" || /sud\.(gov\.)?kz/.test(url)) return { key: "court", name: "Судебный кабинет", url: "https://office.sud.kz" };
  if (url) return { key: "site", name: new URL(url).hostname.replace(/^www\./, ""), url };
  return null;
}

/** «Подать онлайн»: the document is filed on the state portal in the person's own name, in three steps —
 *  take the file and the cover text, open the portal, mark it filed. The portal signs with ЭЦП / eGov Mobile. */
function SubmitOnline({ caseId, a }: { caseId: string; a: CaseAction }) {
  const t = useT();
  const portal = portalOf(a);
  const [copied, setCopied] = useState(false);
  const [done, setDone] = useState<Set<number>>(new Set());
  if (!portal) return null;
  const pname = portal.key === "court" ? t("submit.courtName") : portal.name;
  const mark = (i: number) => setDone((d) => new Set(d).add(i));
  const pdf = `/v1/cases/${caseId}/actions/${a.id}/document?format=${a.has_pdf ? "pdf" : "docx"}`;
  const cover = t("submit.cover", { title: a.title, to: a.addressee?.name ?? "" });
  const step = (i: number, title: string, body: React.ReactNode) => (
    <li className="flex gap-3">
      <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${done.has(i) ? "bg-ink text-surface" : "border border-line bg-surface text-ink"}`}>
        {done.has(i) ? <Icon name="check" size={14} /> : i}
      </span>
      <div className="min-w-0 flex-1 space-y-2">
        <p className="text-sm font-semibold text-ink">{title}</p>
        {body}
      </div>
    </li>
  );
  return (
    <section className="space-y-3 rounded-2xl border border-line bg-sand p-4" aria-labelledby={`submit-${a.id}`}>
      <div className="space-y-1">
        <h4 id={`submit-${a.id}`} className="flex items-center gap-2 font-semibold text-ink"><Icon name="send" size={18} />{t("submit.title", { portal: pname })}</h4>
        <p className="text-xs text-muted">{t(`submit.lead.${portal.key}`)}</p>
      </div>
      <ol className="space-y-4">
        {step(1, t("submit.s1"), (
          <div className="flex flex-wrap gap-2">
            <button type="button" className="btn-ghost min-h-10" onClick={async () => { await downloadFile(pdf, `${a.action_id}.${a.has_pdf ? "pdf" : "docx"}`); mark(1); }}>
              <Icon name="download" size={16} />{t("submit.download")}
            </button>
            <button type="button" className="btn-ghost min-h-10" onClick={async () => {
              try { await navigator.clipboard.writeText(cover); setCopied(true); mark(1); setTimeout(() => setCopied(false), 2500); } catch {}
            }}>
              <Icon name={copied ? "check" : "document"} size={16} />{copied ? t("submit.copied") : t("submit.copy")}
            </button>
          </div>
        ))}
        {step(2, t("submit.s2", { portal: pname }), (
          <>
            <a href={portal.url} target="_blank" rel="noreferrer" onClick={() => mark(2)} className="btn-primary min-h-11 w-full sm:w-auto">
              {t("submit.open", { portal: pname })}<Icon name="external" size={16} />
            </a>
            <p className="text-xs text-muted">{t(`submit.how.${portal.key}`, { to: a.addressee?.name ?? "" })}</p>
          </>
        ))}
        {step(3, t("submit.s3"), <p className="text-xs text-muted">{t("submit.s3hint", { btn: t("case.submitted") })}</p>)}
      </ol>
    </section>
  );
}

/** One step: «**Что сделать.** Как это сделать» — the heading on its own line in bold, so the person sees at a glance
 *  whether to read on (owner 02.10); a step without a heading stays plain text. */
function Step({ text }: { text: string }) {
  const m = /^\*\*(.+?)\*\*\s*([\s\S]*)$/.exec(text);
  if (!m) return <Linkified text={text} />;
  return (
    <>
      <span className="block font-semibold text-ink">{m[1]}</span>
      {m[2] && <span className="block text-muted"><Linkified text={m[2]} /></span>}
    </>
  );
}

/** Plain text with http(s) links made clickable (filing portals in the instructions). */
function Linkified({ text }: { text: string }) {
  const parts = text.split(/(https?:\/\/[^\s),;]+)/g);
  return (
    <>
      {parts.map((p, i) => (/^https?:\/\//.test(p)
        ? <a key={i} href={p} target="_blank" rel="noreferrer" className="link">{p.replace(/^https?:\/\//, "")}</a>
        : <span key={i}>{p}</span>))}
    </>
  );
}
