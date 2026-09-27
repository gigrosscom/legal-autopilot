"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useRef, useState } from "react";
import { EmergencyPanel } from "@/components/EmergencyPanel";
import { LevelBadge, LevelExplainer } from "@/components/LevelBadge";
import RoadmapView from "@/components/Roadmap";
import { SignDocument } from "@/components/SignDocument";
import { StageProgress } from "@/components/StageProgress";
import { Alert, Badge, Button, Icon } from "@/components/ui";
import {
  api,
  downloadFile,
  errorText,
  type CaseAction,
  type CaseView,
  type Emergency,
  type ForumOption,
  type Proposal,
  type Reply,
} from "@/lib/api";
import { useLang, useT } from "@/lib/i18n";

type Msg = { from: "bot" | "user"; text: string };

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
  const t = useT();
  const [c, setCase] = useState<CaseView | null>(null);
  const [log, setLog] = useState<Msg[]>([]);
  const [answer, setAnswer] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [emergency, setEmergency] = useState<Emergency | null>(null);
  const [pendingEvidence, setPendingEvidence] = useState<{ id: string; facts: Record<string, string> } | null>(null);
  const [responseText, setResponseText] = useState("");
  const [showResponse, setShowResponse] = useState(false);
  const [amount, setAmount] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

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

  useEffect(() => endRef.current?.scrollIntoView({ block: "nearest" }), [log, busy]);

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

  async function sendAnswer(text: string) {
    const ok = await run(async () => {
      push({ from: "user", text });
      setAnswer("");
      applyReply(await api<{ case: CaseView; reply: Reply }>(`/v1/cases/${id}/messages`, {
        method: "POST", body: JSON.stringify({ text }),
      }));
    });
    if (!ok) {
      // Not delivered (bad connection): take the message back into the input so nothing is lost.
      setLog((l) => (l.at(-1)?.from === "user" && l.at(-1)?.text === text ? l.slice(0, -1) : l));
      setAnswer(text);
    }
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

  async function upload(file: File) {
    await run(async () => {
      const kind = c?.question?.evidence_kinds?.[0]?.kind ?? "other";
      const form = new FormData();
      form.append("file", file);
      form.append("kind", kind);
      push({ from: "user", text: file.name });
      const out = await api<{ case: CaseView; evidence: { id: string; extracted_facts: Record<string, string> } }>(
        `/v1/cases/${id}/evidence`, { method: "POST", body: form });
      setCase(out.case);
      setPendingEvidence({ id: out.evidence.id, facts: out.evidence.extracted_facts });
    });
  }

  async function confirmEvidence() {
    if (!pendingEvidence) return;
    await run(async () => {
      const out = await api<{ case: CaseView; reply: Reply }>(`/v1/cases/${id}/evidence/${pendingEvidence.id}/confirm`, {
        method: "POST", body: JSON.stringify({}),
      });
      setPendingEvidence(null);
      applyReply(out);
    });
  }

  async function post(path: string, body: unknown = {}) {
    await run(async () => {
      const out = await api<{ case: CaseView; proposal?: Proposal }>(`/v1/cases/${id}${path}`, {
        method: "POST", body: JSON.stringify(body),
      });
      setCase(out.case);
    });
  }

  if (error && !c) return <Alert tone="danger" role="alert">{error}</Alert>;
  if (!c) return <p className="text-muted">{t("common.loading")}</p>;

  const last = c.actions.at(-1);
  const proposal = c.proposal;
  const q = c.question;
  const cov = c.coverage;
  const choosingForum = c.status === "intake" && !c.scenario && cov.options.length > 0;
  const ack = c.status === "intake" ? c.safety.pending_ack : null;
  const title = c.scenario?.title ?? cov.dispute?.title ?? t("case.untitled");

  return (
    <div className="grid gap-8 lg:grid-cols-[1fr_320px]">
      <div className="min-w-0 space-y-5">
        <div className="space-y-3">
          <Link href="/cases" className="inline-flex items-center gap-1 text-sm text-muted hover:text-brand">
            <Icon name="arrowRight" size={16} className="rotate-180 rtl:rotate-0" />{t("case.back")}
          </Link>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="me-auto text-2xl font-bold tracking-tight">{title}</h1>
            <LevelBadge level={cov.level} />
            <Badge>{c.status_label}</Badge>
          </div>
          <StageProgress stage={c.stage} />
        </div>

        {emergency && <EmergencyPanel info={emergency} onContinue={() => setEmergency(null)} />}

        <div className="card space-y-3">
          <LevelExplainer level={cov.level} />
          <Link href="/how-it-works" className="link inline-flex items-center gap-1 text-sm">
            {t("cta.more")}<Icon name="arrowRight" size={14} className="rtl:-scale-x-100" />
          </Link>
          {cov.reasons.length > 0 && (
            <ul className="flex flex-wrap gap-2">{cov.reasons.map((r) => <li key={r.code}><Badge tone="warning">{r.label}</Badge></li>)}</ul>
          )}
          {cov.forum && (
            <p className="flex items-center gap-2 text-sm"><Icon name="building" size={18} className="text-brand" />{cov.forum.name}</p>
          )}
        </div>

        {c.safety.hold_reason && <Alert tone="warning" title={t("case.holdTitle")}>{c.safety.hold_message}</Alert>}
        {c.scenario?.draft_disclaimer && <Alert tone="draft" title={t("case.draftTitle")}>{c.scenario.draft_disclaimer}</Alert>}

        {ack && (
          <Alert tone={ack === "false_report" ? "warning" : "info"} title={t(`ack.${ack}.title`)}
            actions={<Button disabled={busy} onClick={() => acknowledge(ack)} icon="check">{t(`ack.${ack}.button`)}</Button>}>
            {log.at(-1)?.from === "bot" && log.at(-1)?.text ? log.at(-1)!.text : t(`ack.${ack}.text`)}
          </Alert>
        )}

        {c.status === "handed_to_lawyer" && cov.level === "lawyer" && (
          <Alert tone="info" icon="lawyer" title={t("case.lawyerTitle")}
            actions={<Button href="/lawyers" variant="secondary" iconEnd="arrowRight">{t("case.lawyerCta")}</Button>}>
            {log.find((m) => m.from === "bot")?.text ?? t("case.lawyerText")}
          </Alert>
        )}

        {choosingForum && <ForumChoice options={cov.options} busy={busy} onChoose={chooseForum} />}

        {/* interview */}
        {c.status === "intake" && !choosingForum && !ack && (
          <div className="card space-y-3">
            <div className="max-h-[440px] space-y-2 overflow-y-auto" aria-live="polite">
              {log.map((m, i) => (
                <div key={i} className={`flex ${m.from === "user" ? "justify-end" : ""}`}>
                  <div className={`max-w-[85%] whitespace-pre-line rounded-2xl px-4 py-2 text-sm ${m.from === "user" ? "bg-brand text-white" : "bg-sand"}`}>
                    {m.text}
                  </div>
                </div>
              ))}
              {busy && (
                <div className="flex">
                  <div className="flex items-center gap-2 rounded-2xl bg-sand px-4 py-2 text-sm text-muted">
                    <Icon name="spinner" size={16} />{t("case.thinking")}
                  </div>
                </div>
              )}
              <div ref={endRef} />
            </div>

            {pendingEvidence && (
              <div className="rounded-xl bg-brand-50 p-3 text-sm">
                {Object.keys(pendingEvidence.facts).length > 0 ? (
                  <>
                    <p className="mb-1 font-semibold">{t("case.found")}:</p>
                    <ul className="mb-2 list-inside list-disc">
                      {Object.entries(pendingEvidence.facts).map(([k, v]) => (
                        <li key={k}>{c.facts.find((f) => f.field === k)?.label ?? k}: {v}</li>
                      ))}
                    </ul>
                  </>
                ) : (
                  <p className="mb-2">{t("case.nothingFound")}</p>
                )}
                <Button disabled={busy} onClick={confirmEvidence} icon="check">{t("case.confirm")}</Button>
              </div>
            )}

            {!pendingEvidence && (
              <div className="space-y-2">
                {/* One form element for both "tell us more" and field answers: swapping whole forms
                    under a focused input breaks pages when browser extensions have touched the DOM. */}
                <form className={q?.type === "evidence" ? "hidden" : q ? "flex flex-col gap-2 sm:flex-row" : "space-y-2"}
                  onSubmit={(e) => { e.preventDefault(); if (answer.trim()) sendAnswer(answer.trim()); }}>
                  {q ? (
                    <>
                      <label htmlFor="answer" className="sr-only">{q.text}</label>
                      <input id="answer" key="answer" className="input" autoFocus type="text" value={answer}
                        inputMode={q.type === "date" ? "numeric" : undefined}
                        placeholder={q.type === "date" ? t("case.datePlaceholder") : t("case.answerPlaceholder")}
                        onChange={(e) => setAnswer(e.target.value)} />
                    </>
                  ) : (
                    <>
                      <label htmlFor="more" className="sr-only">{t("case.more")}</label>
                      <textarea id="more" key="more" className="input min-h-24" autoFocus placeholder={t("case.morePlaceholder")}
                        value={answer} onChange={(e) => setAnswer(e.target.value)} />
                    </>
                  )}
                  <Button className={q ? "shrink-0" : undefined} disabled={busy || !answer.trim()} icon="send">
                    {q ? t("case.send") : t("case.more")}
                  </Button>
                </form>
                {q && (
                <div className="flex flex-wrap items-center gap-2">
                  <label className="btn-ghost cursor-pointer">
                    <Icon name="upload" size={18} />{t("case.upload")}
                    <input type="file" accept="image/*,application/pdf,text/plain" className="sr-only"
                      onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
                  </label>
                  {q.optional && (
                    <Button variant="secondary" disabled={busy} onClick={() => sendAnswer("пропустить")}>{t("case.skip")}</Button>
                  )}
                  <span className="text-xs text-muted">{t("case.uploadHint")}</span>
                </div>
                )}
              </div>
            )}
          </div>
        )}

        {c.roadmap && <RoadmapView roadmap={c.roadmap} />}

        {c.actions.map((a) => <ActionCard key={a.id} caseId={c.id} a={a} />)}

        {/* next step */}
        {c.status !== "intake" && (
          <div className="card space-y-3">
            {c.status === "qualified" && (
              <Button disabled={busy} onClick={() => post("/actions/next")} icon="document">{t("case.prepare")}</Button>
            )}

            {c.status === "action_ready" && last && (
              last.approval_status === "pending" || last.approval_status === "rejected" ? (
                <p className="flex items-center gap-2 text-sm">
                  <Icon name="lawyer" size={18} className="text-brand" />
                  {last.approval_status === "pending" ? t("case.awaitingApproval") : t("case.rejected")}
                </p>
              ) : (
                <div className="flex flex-wrap gap-2">
                  <Button disabled={busy} icon="check" onClick={() => post(`/actions/${last.id}/submitted`, { via: "user_submits" })}>
                    {t("case.submitted")}
                  </Button>
                  {last.email_allowed && last.addressee?.email && (
                    <Button variant="secondary" disabled={busy} icon="mail" onClick={() => post(`/actions/${last.id}/submitted`, { via: "email" })}>
                      {t("case.sendEmail")}
                    </Button>
                  )}
                </div>
              )
            )}

            {c.status === "awaiting_response" && last && proposal && (
              <>
                {proposal.message && <p className="text-sm">{proposal.message}</p>}
                {proposal.type === "wait" && !showResponse && (
                  <div className="flex flex-wrap gap-2">
                    <Button icon="mail" onClick={() => setShowResponse(true)}>{t("case.gotResponse")}</Button>
                    <Button variant="secondary" disabled={busy} icon="hourglass"
                      onClick={() => post(`/actions/${last.id}/response`, { no_response: true })}>{t("case.noResponse")}</Button>
                  </div>
                )}
                {proposal.type === "wait" && showResponse && (
                  <div className="space-y-2">
                    <label htmlFor="resp" className="sr-only">{t("case.responsePlaceholder")}</label>
                    <textarea id="resp" className="input" rows={5} placeholder={t("case.responsePlaceholder")}
                      value={responseText} onChange={(e) => setResponseText(e.target.value)} />
                    <div className="flex flex-wrap items-center gap-2">
                      <Button disabled={busy || !responseText.trim()}
                        onClick={() => post(`/actions/${last.id}/response`, { text: responseText }).then(() => setShowResponse(false))}>
                        {t("case.responseSend")}
                      </Button>
                      <label className="btn-ghost cursor-pointer">
                        <Icon name="upload" size={18} />{t("case.responseFile")}
                        <input type="file" accept="image/*,application/pdf,text/plain" className="sr-only"
                          onChange={(e) => {
                            const f = e.target.files?.[0];
                            if (!f) return;
                            run(async () => {
                              const form = new FormData();
                              form.append("file", f);
                              const out = await api<{ case: CaseView }>(`/v1/cases/${id}/actions/${last.id}/response/file`, { method: "POST", body: form });
                              setCase(out.case);
                              setShowResponse(false);
                            });
                          }} />
                      </label>
                    </div>
                  </div>
                )}
                {proposal.type === "clarify" && (
                  <div className="flex flex-wrap gap-2">
                    {(["full", "partial", "refusal", "none"] as const).map((cls) => (
                      <Button key={cls} variant="secondary" disabled={busy}
                        onClick={() => post(`/actions/${last.id}/response`, { response_class: cls })}>{t(`case.classes.${cls}`)}</Button>
                    ))}
                  </div>
                )}
                {(proposal.type === "prepare_action" || proposal.type === "handoff") && (
                  <Button disabled={busy} icon={proposal.type === "handoff" ? "lawyer" : "document"} onClick={() => post("/actions/next")}>
                    {proposal.type === "handoff" ? t("case.handoff") : proposal.title}
                  </Button>
                )}
                {proposal.type !== "wait" && proposal.type !== "clarify" && (
                  <div className="space-y-2 border-t border-line pt-3">
                    <p className="text-sm font-semibold">{t("case.close")}</p>
                    <label htmlFor="amount" className="sr-only">{t("case.amountRecovered")}</label>
                    <input id="amount" className="input max-w-xs" inputMode="decimal"
                      placeholder={`${t("case.amountRecovered")}, ${c.currency ?? ""}`} value={amount} onChange={(e) => setAmount(e.target.value)} />
                    <div className="flex flex-wrap gap-2">
                      {(["won", "partial", "lost"] as const).map((r) => (
                        <Button key={r} variant={r === proposal.suggested_result ? "primary" : "secondary"} disabled={busy}
                          onClick={() => post("/close", { result: r, amount_recovered: amount || (r === "won" ? c.amount_at_stake : null) })}>
                          {t(`case.close${r[0].toUpperCase()}${r.slice(1)}`)}
                        </Button>
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}

            {c.status === "handed_to_lawyer" && cov.level !== "lawyer" && (
              <p className="flex items-center gap-2 text-sm"><Icon name="lawyer" size={18} className="text-brand" />{proposal?.message || c.status_label}</p>
            )}

            {c.outcome && (
              <div className="text-sm">
                <p className="font-semibold">{t("case.outcome")}: {c.outcome.result}</p>
                {c.outcome.amount_recovered && <p>{c.outcome.amount_recovered} {c.outcome.currency}</p>}
                <p className="text-muted">{c.outcome.days_to_resolution} {t("case.days")}</p>
              </div>
            )}
          </div>
        )}
        {error && <Alert tone="danger" role="alert">{error}</Alert>}
        {busy && c.status !== "intake" && <p className="flex items-center gap-2 text-sm text-muted"><Icon name="spinner" size={16} />{t("case.working")}</p>}
      </div>

      <aside className="space-y-4">
        {c.facts.length > 0 && (
          <div className="card space-y-2">
            <h2 className="font-semibold">{t("case.facts")}</h2>
            <dl className="space-y-1.5 text-sm">
              {c.facts.map((f) => (
                <div key={f.field}>
                  <dt className="text-xs text-muted">{f.label}</dt>
                  <dd className="break-words">{f.value}</dd>
                </div>
              ))}
            </dl>
            {c.evidence.length > 0 && (
              <ul className="space-y-1 border-t border-line pt-2 text-xs text-muted">
                {c.evidence.map((e) => <li key={e.id} className="flex items-center gap-1"><Icon name="document" size={14} />{e.filename}</li>)}
              </ul>
            )}
          </div>
        )}
        {cov.upl_notice && <Alert tone="info" icon="info" title={t("case.uplTitle")}>{cov.upl_notice}</Alert>}
        {!(c.status === "handed_to_lawyer" && cov.level === "lawyer") && (
          <div className="card space-y-2 text-sm">
            <h2 className="flex items-center gap-2 font-semibold"><Icon name="lawyer" size={18} className="text-brand" />{t("cta.caseLawyerTitle")}</h2>
            <p className="text-muted">{t("cta.caseLawyerText")}</p>
            <Button href="/lawyers" variant="secondary" className="w-full" icon="lawyer">{t("cta.lawyer")}</Button>
          </div>
        )}
        <div className="rounded-2xl border border-line bg-surface p-4 text-xs text-muted">
          <p className="flex items-center gap-1.5 font-semibold text-ink"><Icon name="info" size={16} />{c.ai_label}</p>
          <p className="mt-1">{c.service_disclaimer}</p>
        </div>
      </aside>
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

function ActionCard({ caseId, a }: { caseId: string; a: CaseAction }) {
  const t = useT();
  const { lang } = useLang();
  if (a.kind === "handoff") {
    return <div className="card flex items-center gap-2 text-sm"><Icon name="lawyer" className="text-brand" />{a.title}</div>;
  }
  return (
    <div className="card space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-semibold">{a.sequence}. {a.title}</h3>
        {a.response_label && <Badge>{t("case.response")}: {a.response_label}</Badge>}
      </div>
      {a.addressee?.name && <p className="flex items-center gap-1.5 text-sm text-muted"><Icon name="building" size={16} />{a.addressee.name}</p>}
      {a.downloadable && (
        <div className="flex flex-wrap gap-2">
          {a.has_pdf && (
            <Button variant="secondary" icon="download"
              onClick={() => downloadFile(`/v1/cases/${caseId}/actions/${a.id}/document?format=pdf`, `${a.action_id}.pdf`)}>PDF</Button>
          )}
          <Button variant="secondary" icon="download"
            onClick={() => downloadFile(`/v1/cases/${caseId}/actions/${a.id}/document?format=docx`, `${a.action_id}.docx`)}>DOCX</Button>
        </div>
      )}
      {a.downloadable && (
        <SignDocument caseId={caseId} actionId={a.id} fileBase={a.action_id} initial={a.signatures ?? []} />
      )}
      {a.downloadable && a.instructions.length > 0 && (
        <div className="space-y-2">
          <p className="text-sm font-semibold">{t("case.instructions")}</p>
          <ol className="space-y-2 text-sm">
            {a.instructions.map((s, i) => (
              <li key={i} className="flex gap-3">
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-50 text-xs font-bold text-brand">{i + 1}</span>
                <span className="min-w-0 break-words pt-0.5"><Linkified text={s} /></span>
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
