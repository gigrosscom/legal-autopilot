"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useRef, useState } from "react";
import { api, downloadFile, type CaseAction, type CaseView, type Proposal, type Reply, errorText } from "@/lib/api";
import { useT } from "@/lib/i18n";
import RoadmapView from "@/components/Roadmap";

type Msg = { from: "bot" | "user"; text: string };

const replyKey = (id: string) => `konsilier.reply.${id}`;
function readReply(id: string): string | null {
  try {
    return sessionStorage.getItem(replyKey(id));
  } catch {
    return null;
  }
}
function saveReply(id: string, text: string) {
  try {
    sessionStorage.setItem(replyKey(id), text);
  } catch {}
}

export default function CasePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const t = useT();
  const [c, setCase] = useState<CaseView | null>(null);
  const [log, setLog] = useState<Msg[]>([]);
  const [answer, setAnswer] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
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
        const last = readReply(id);
        const initial: Msg[] = [];
        // The stored reply may be stale (e.g. "tell me more" before the case was qualified):
        // show it only if it still leads to the question the case is waiting for.
        if (last && (!view.question || last.includes(view.question.text))) initial.push({ from: "bot", text: last });
        else if (view.question) initial.push({ from: "bot", text: view.question.text });
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

  async function sendAnswer(text: string) {
    const ok = await run(async () => {
      push({ from: "user", text });
      setAnswer("");
      const out = await api<{ case: CaseView; reply: Reply }>(`/v1/cases/${id}/messages`, {
        method: "POST",
        body: JSON.stringify({ text }),
      });
      setCase(out.case);
      push({ from: "bot", text: out.reply.message });
      saveReply(id, out.reply.message);
    });
    if (!ok) {
      // Not delivered (bad connection): take the message back into the input so nothing is lost.
      setLog((l) => (l.at(-1)?.from === "user" && l.at(-1)?.text === text ? l.slice(0, -1) : l));
      setAnswer(text);
    }
  }

  async function upload(file: File) {
    await run(async () => {
      const kind = c?.question?.evidence_kinds?.[0]?.kind ?? "other";
      const form = new FormData();
      form.append("file", file);
      form.append("kind", kind);
      push({ from: "user", text: `📎 ${file.name}` });
      const out = await api<{ case: CaseView; evidence: { id: string; extracted_facts: Record<string, string> } }>(
        `/v1/cases/${id}/evidence`,
        { method: "POST", body: form },
      );
      setCase(out.case);
      setPendingEvidence({ id: out.evidence.id, facts: out.evidence.extracted_facts });
    });
  }

  async function confirmEvidence() {
    if (!pendingEvidence) return;
    await run(async () => {
      const out = await api<{ case: CaseView; reply: Reply }>(`/v1/cases/${id}/evidence/${pendingEvidence.id}/confirm`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      setPendingEvidence(null);
      setCase(out.case);
      if (out.reply.message) {
        push({ from: "bot", text: out.reply.message });
        saveReply(id, out.reply.message);
      }
    });
  }

  async function post(path: string, body: unknown = {}) {
    await run(async () => {
      const out = await api<{ case: CaseView; proposal?: Proposal }>(`/v1/cases/${id}${path}`, {
        method: "POST",
        body: JSON.stringify(body),
      });
      setCase(out.case);
    });
  }

  if (error && !c) return <p className="text-red-600">{error}</p>;
  if (!c) return <p className="text-ink/50">{t("common.loading")}</p>;

  const last = c.actions.at(-1);
  const proposal = c.proposal;
  const q = c.question;

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
      <div className="space-y-5">
        <div className="flex items-center justify-between gap-3">
          <div>
            <Link href="/cases" className="text-sm text-ink/50 hover:text-brand">← {t("case.back")}</Link>
            <h1 className="text-2xl font-bold">{c.scenario?.title ?? "…"}</h1>
          </div>
          <span className="chip">{c.status_label}</span>
        </div>

        {c.scenario?.draft_disclaimer && (
          <div className="rounded-xl border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">⚠️ {c.scenario.draft_disclaimer}</div>
        )}

        {/* interview */}
        {(c.status === "intake" || pendingEvidence) && (
          <div className="card space-y-3">
            <div className="max-h-[420px] space-y-2 overflow-y-auto">
              {log.map((m, i) => (
                <div key={i} className={`flex ${m.from === "user" ? "justify-end" : ""}`}>
                  <div className={`max-w-[85%] whitespace-pre-line rounded-2xl px-4 py-2 text-sm ${m.from === "user" ? "bg-brand text-white" : "bg-ink/5"}`}>
                    {m.text}
                  </div>
                </div>
              ))}
              {busy && (
                <div className="flex">
                  <div className="rounded-2xl bg-ink/5 px-4 py-2 text-sm text-ink/60">⏳ {t("case.thinking")}</div>
                </div>
              )}
              <div ref={endRef} />
            </div>

            {pendingEvidence && (
              <div className="rounded-xl bg-brand/5 p-3 text-sm">
                {Object.keys(pendingEvidence.facts).length > 0 ? (
                  <>
                    <div className="mb-1 font-semibold">{t("case.found")}:</div>
                    <ul className="mb-2 list-inside list-disc">
                      {Object.entries(pendingEvidence.facts).map(([k, v]) => (
                        <li key={k}>{c.facts.find((f) => f.field === k)?.label ?? k}: {v}</li>
                      ))}
                    </ul>
                  </>
                ) : (
                  <p className="mb-2">{t("case.nothingFound")}</p>
                )}
                <button className="btn-primary" disabled={busy} onClick={confirmEvidence}>{t("case.confirm")}</button>
              </div>
            )}

            {c.status === "intake" && !pendingEvidence && (
              <div className="space-y-2">
                {/* One form element for both "tell us more" and field answers: swapping whole forms
                    under a focused input breaks pages when browser extensions have touched the DOM. */}
                <form
                  className={q?.type === "evidence" ? "hidden" : q ? "flex flex-col gap-2 sm:flex-row" : "space-y-2"}
                  onSubmit={(e) => {
                    e.preventDefault();
                    if (answer.trim()) sendAnswer(answer.trim());
                  }}
                >
                  {q ? (
                    <input
                      key="answer"
                      className="input"
                      autoFocus
                      type="text"
                      inputMode={q.type === "date" ? "numeric" : undefined}
                      placeholder={q.type === "date" ? t("case.datePlaceholder") : t("case.answerPlaceholder")}
                      value={answer}
                      onChange={(e) => setAnswer(e.target.value)}
                    />
                  ) : (
                    <textarea
                      key="more"
                      className="input min-h-24"
                      autoFocus
                      placeholder={t("case.morePlaceholder")}
                      value={answer}
                      onChange={(e) => setAnswer(e.target.value)}
                    />
                  )}
                  <button className={q ? "btn-primary shrink-0" : "btn-primary"} disabled={busy || !answer.trim()}>
                    {q ? t("case.send") : t("case.more")}
                  </button>
                </form>
                {q && (
                  <div className="flex flex-wrap items-center gap-2">
                    <label className="btn-ghost cursor-pointer">
                      📎 {t("case.upload")}
                      <input
                        type="file"
                        accept="image/*,application/pdf,text/plain"
                        className="hidden"
                        onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])}
                      />
                    </label>
                    {q.optional && (
                      <button className="btn-ghost" disabled={busy} onClick={() => sendAnswer("пропустить")}>{t("case.skip")}</button>
                    )}
                    <span className="text-xs text-ink/50">{t("case.uploadHint")}</span>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {c.roadmap && <RoadmapView roadmap={c.roadmap} />}

        {/* documents & steps */}
        {c.actions.map((a) => (
          <ActionCard key={a.id} caseId={c.id} a={a} />
        ))}

        {/* next step */}
        <div className={`card space-y-3 ${c.status === "intake" && !error ? "hidden" : ""}`}>
          {c.status === "qualified" && (
            <button className="btn-primary" disabled={busy} onClick={() => post("/actions/next")}>📄 {t("case.prepare")}</button>
          )}

          {c.status === "action_ready" && last && (
            last.approval_status === "pending" || last.approval_status === "rejected" ? (
              <p className="text-sm">{last.approval_status === "pending" ? t("case.awaitingApproval") : t("case.rejected")}</p>
            ) : (
              <div className="flex flex-wrap gap-2">
                <button className="btn-primary" disabled={busy} onClick={() => post(`/actions/${last.id}/submitted`, { via: "user_submits" })}>
                  ✅ {t("case.submitted")}
                </button>
                {last.email_allowed && last.addressee?.email && (
                  <button className="btn-ghost" disabled={busy} onClick={() => post(`/actions/${last.id}/submitted`, { via: "email" })}>
                    📧 {t("case.sendEmail")}
                  </button>
                )}
              </div>
            )
          )}

          {c.status === "awaiting_response" && last && proposal && (
            <>
              {proposal.message && <p className="text-sm">{proposal.message}</p>}
              {proposal.type === "wait" && !showResponse && (
                <div className="flex flex-wrap gap-2">
                  <button className="btn-primary" onClick={() => setShowResponse(true)}>📨 {t("case.gotResponse")}</button>
                  <button className="btn-ghost" disabled={busy} onClick={() => post(`/actions/${last.id}/response`, { no_response: true })}>
                    🕳 {t("case.noResponse")}
                  </button>
                </div>
              )}
              {proposal.type === "wait" && showResponse && (
                <div className="space-y-2">
                  <textarea className="input" rows={5} placeholder={t("case.responsePlaceholder")} value={responseText} onChange={(e) => setResponseText(e.target.value)} />
                  <div className="flex flex-wrap items-center gap-2">
                    <button
                      className="btn-primary"
                      disabled={busy || !responseText.trim()}
                      onClick={() => post(`/actions/${last.id}/response`, { text: responseText }).then(() => setShowResponse(false))}
                    >
                      {t("case.responseSend")}
                    </button>
                    <label className="btn-ghost cursor-pointer">
                      📎 {t("case.responseFile")}
                      <input
                        type="file"
                        accept="image/*,application/pdf,text/plain"
                        className="hidden"
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
                        }}
                      />
                    </label>
                  </div>
                </div>
              )}
              {proposal.type === "clarify" && (
                <div className="flex flex-wrap gap-2">
                  {(["full", "partial", "refusal", "none"] as const).map((cls) => (
                    <button key={cls} className="btn-ghost" disabled={busy} onClick={() => post(`/actions/${last.id}/response`, { response_class: cls })}>
                      {t(`case.classes.${cls}`)}
                    </button>
                  ))}
                </div>
              )}
              {(proposal.type === "prepare_action" || proposal.type === "handoff") && (
                <button className="btn-primary" disabled={busy} onClick={() => post("/actions/next")}>
                  {proposal.type === "handoff" ? `👩‍⚖️ ${t("case.handoff")}` : `📄 ${proposal.title}`}
                </button>
              )}
              {proposal.type !== "wait" && proposal.type !== "clarify" && (
                <div className="space-y-2 border-t border-ink/10 pt-3">
                  <div className="text-sm font-semibold">{t("case.close")}</div>
                  <input className="input max-w-xs" inputMode="decimal" placeholder={`${t("case.amountRecovered")}, ${c.currency ?? ""}`} value={amount} onChange={(e) => setAmount(e.target.value)} />
                  <div className="flex flex-wrap gap-2">
                    {(["won", "partial", "lost"] as const).map((r) => (
                      <button
                        key={r}
                        className={r === proposal.suggested_result ? "btn-primary" : "btn-ghost"}
                        disabled={busy}
                        onClick={() => post("/close", { result: r, amount_recovered: amount || (r === "won" ? c.amount_at_stake : null) })}
                      >
                        {t(`case.close${r[0].toUpperCase()}${r.slice(1)}`)}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}

          {c.status === "handed_to_lawyer" && <p className="text-sm">👩‍⚖️ {proposal?.message || c.status_label}</p>}

          {c.outcome && (
            <div className="text-sm">
              <div className="font-semibold">{t("case.outcome")}: {c.outcome.result}</div>
              {c.outcome.amount_recovered && <div>{c.outcome.amount_recovered} {c.outcome.currency}</div>}
              <div className="text-ink/50">{c.outcome.days_to_resolution} {t("case.days")}</div>
            </div>
          )}
          {error && <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-red-700">{error}</p>}
          {busy && <p className="text-sm text-ink/60">⏳ {t("case.working")}</p>}
        </div>
      </div>

      <aside className="space-y-4">
        <div className="card space-y-2">
          <h2 className="font-semibold">{t("case.facts")}</h2>
          <dl className="space-y-1.5 text-sm">
            {c.facts.map((f) => (
              <div key={f.field}>
                <dt className="text-xs text-ink/50">{f.label}</dt>
                <dd className="break-words">{f.value}</dd>
              </div>
            ))}
          </dl>
          {c.evidence.length > 0 && (
            <ul className="border-t border-ink/10 pt-2 text-xs text-ink/60">
              {c.evidence.map((e) => <li key={e.id}>📎 {e.filename}</li>)}
            </ul>
          )}
        </div>
        <div className="rounded-xl bg-ink/5 p-3 text-xs text-ink/60">
          <p className="font-semibold">🤖 {c.ai_label}</p>
          <p className="mt-1">{c.service_disclaimer}</p>
        </div>
      </aside>
    </div>
  );
}

function ActionCard({ caseId, a }: { caseId: string; a: CaseAction }) {
  const t = useT();
  if (a.kind === "handoff") {
    return <div className="card text-sm">👩‍⚖️ {a.title}</div>;
  }
  return (
    <div className="card space-y-3">
      <div className="flex items-center justify-between gap-2">
        <h3 className="font-semibold">{a.sequence}. {a.title}</h3>
        {a.response_label && <span className="chip">{t("case.response")}: {a.response_label}</span>}
      </div>
      {a.addressee?.name && <p className="text-sm text-ink/70">→ {a.addressee.name}</p>}
      {a.downloadable && (
        <div className="flex gap-2">
          {a.has_pdf && (
            <button className="btn-ghost" onClick={() => downloadFile(`/v1/cases/${caseId}/actions/${a.id}/document?format=pdf`, `${a.action_id}.pdf`)}>
              ⬇ PDF
            </button>
          )}
          <button className="btn-ghost" onClick={() => downloadFile(`/v1/cases/${caseId}/actions/${a.id}/document?format=docx`, `${a.action_id}.docx`)}>
            ⬇ DOCX
          </button>
        </div>
      )}
      {a.downloadable && a.instructions.length > 0 && (
        <div>
          <div className="text-sm font-semibold">{t("case.instructions")}</div>
          <ol className="list-inside list-decimal space-y-1 text-sm">
            {a.instructions.map((s, i) => <li key={i}>{s}</li>)}
          </ol>
        </div>
      )}
      {a.deadline && (
        <p className="text-sm">
          ⏰ {t("case.deadline")}: <b>{new Date(a.deadline.due_date).toLocaleDateString("ru-RU")}</b>
          <span className="ml-2 chip">{t(`case.deadlineStatus.${a.deadline.status}`)}</span>
        </p>
      )}
      {a.response_summary && <p className="text-sm text-ink/60">«{a.response_summary}»</p>}
    </div>
  );
}
