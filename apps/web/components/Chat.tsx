"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { LAST_CASE_KEY } from "@/components/AppNav";
import { AppShell, type MoreLink, type MoreSection } from "@/components/AppShell";
import { Composer, type Attached } from "@/components/Composer";
import { EmergencyPanel } from "@/components/EmergencyPanel";
import { Bubble } from "@/components/Bubble";
import { Markdown } from "@/components/Markdown";
import { Invite } from "@/components/Invite";
import { Icon, type IconName } from "@/components/ui";
import { ApiError, api, errorText, publicApi, type CaseView, type Emergency, type Reply } from "@/lib/api";
import { chatHistory, sendChat, type ChatMessage } from "@/lib/chat";
import { LAWYERS_PUBLIC } from "@/lib/features";
import { useLang, useT } from "@/lib/i18n";
import { TERMS_VERSION, markTermsAccepted, termsAccepted } from "@/lib/legal/terms";
import { SITUATIONS } from "@/lib/situations";
import { canSpeak, speak, stopSpeaking } from "@/lib/voice";

/** The count of free messages left shows once this many or fewer remain (e.g. after the 30th of 40). */
const REMAINING_FROM = 10;
/** The marker a reply ends with when it offers a document; hidden while the reply streams in. */
const OFFER = /\[?\[\s*DOC[A-Z]*\s*\]?\]?\s*$|\[\[?\s*$/;
// labels a model may copy from its instructions («SHORT ANSWER:», «DETAILS:») never reach the screen
const LABELS = /^\s*\**\s*(SHORT ANSWER|DETAILS|КРАТКИЙ ОТВЕТ|ПОДРОБНОСТИ)\s*\**\s*:\s*\**\s*/gim;
const clean = (text: string) => text.replace(OFFER, "").replace(LABELS, "").trimEnd();
/** Between the short answer and the details (konsilier/chat.py MORE_MARKER); a half-typed one while streaming too. */
const MORE = /\[?\[\s*MORE\s*\]?\]?/i;
const MORE_ALL = /\[?\[\s*MORE\s*\]?\]?/gi;
const MORE_TAIL = /\[\[?\s*M?O?R?E?\s*\]?$/i;
/** Without the marker, a long reply still opens short: its first paragraph, the rest under «Подробнее». */
const LONG_WORDS = 70;

/** The short answer and the details of a reply (null when there is nothing more). */
function splitReply(text: string): [string, string | null] {
  const m = MORE.exec(text);
  if (m) {
    const short = text.slice(0, m.index).trim();
    // QA BUG-05: only the first marker cuts; any later one (after a tool call) is dropped from the details
    const rest = text.slice(m.index + m[0].length).replace(MORE_ALL, "\n\n").replace(/\n{3,}/g, "\n\n").trim();
    return short ? [short, rest || null] : [rest, null];
  }
  const paras = text.trim().split(/\n\s*\n/);
  if (paras.length > 1 && text.split(/\s+/).length > LONG_WORDS) return [paras[0], paras.slice(1).join("\n\n")];
  return [text, null];
}

/** A reply: the short answer, and «Подробнее» that opens the details in place. */
function Reply({ text, streaming = false }: { text: string; streaming?: boolean }) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const cleaned = clean(text);
  if (streaming) {
    // while it types: only the short answer; the details arrive hidden and open with «Подробнее» when it is done
    const m = MORE.exec(cleaned);
    const shown = (m ? cleaned.slice(0, m.index) : cleaned).replace(MORE_TAIL, "").trimEnd();
    return shown ? <Markdown text={shown} /> : null;
  }
  const [short, rest] = splitReply(cleaned);
  return (
    <>
      <Markdown text={short} />
      {rest && (open ? <Markdown text={rest} /> : (
        <button type="button" onClick={() => setOpen(true)} aria-expanded={false}
          className="inline-flex items-center gap-1 text-[15px] font-semibold text-[var(--chat-accent)] hover:underline">
          {t("chat.more")}<Icon name="chevronDown" size={16} />
        </button>
      ))}
    </>
  );
}

const dayOf = (iso: string) => new Date(iso).toDateString();

/** «Сегодня», «Вчера» or the date, between the days of a conversation. */
function DayChip({ iso }: { iso: string }) {
  const t = useT();
  const d = new Date(iso), now = new Date();
  const y = new Date(now); y.setDate(now.getDate() - 1);
  const label = d.toDateString() === now.toDateString() ? t("app.today")
    : d.toDateString() === y.toDateString() ? t("app.yesterday")
    : d.toLocaleDateString([], { weekday: "short", day: "numeric", month: "short" });
  return (
    <div className="flex justify-center py-1">
      <span className="px-3 py-1 text-xs font-medium text-muted">{label}</span>
    </div>
  );
}

/** Greeting by the time of day, as the messengers' assistants do. */
function greeting(t: (k: string) => string) {
  const h = new Date().getHours();
  return t(h < 5 ? "chat.greet.night" : h < 12 ? "chat.greet.morning" : h < 18 ? "chat.greet.day" : "chat.greet.evening");
}

/**
 * The chat, as in the messengers: the conversation as a dialogue, one message box at the bottom. Without a case
 * yet, the first message runs the emergency check and opens the case; the chat then lives at /chat/<id>. A document
 * is offered inside a reply, only when the conversation comes to it.
 */
export function Chat({ caseId: initialCase, draft: initialDraft = "", autoSend = false, hint, situation, files: initialFiles }: {
  caseId: string | null; draft?: string; autoSend?: boolean; hint?: string; situation?: string;
  files?: File[];  // attached from the start: typed on the home page, or shared to the app from another app
}) {
  const t = useT();
  const { lang } = useLang();
  const [caseId, setCaseId] = useState(initialCase);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streaming, setStreaming] = useState<string | null>(null);
  // an answer that broke off (or never came): what was shown stays, «Повторить» sends the same message again
  const [failed, setFailed] = useState<{ partial: string; text: string; files: Attached[] } | null>(null);
  const [left, setLeft] = useState<{ n: number; limit: number } | null>(null);  // free messages left in 24 hours
  const [dailyLimit, setDailyLimit] = useState<number | null>(null);
  const [lookingUp, setLookingUp] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [emergency, setEmergency] = useState<(Emergency & { text: string }) | null>(null);
  const [draft, setDraft] = useState(initialDraft);
  const [files, setFiles] = useState<Attached[]>(() =>
    (initialFiles ?? []).map((f, i) => ({ key: `start-${i}-${f.name}`, filename: f.name, file: f })));
  const [voiceMode, setVoiceMode] = useState(false);
  const [tts, setTts] = useState(false);
  const sentInitial = useRef(false);
  const [showTerms, setShowTerms] = useState(false);  // only until the terms were accepted once
  useEffect(() => setShowTerms(!termsAccepted()), []);
  const abort = useRef<AbortController | null>(null);  // «Стоп» while the answer is being written
  const [speakingId, setSpeakingId] = useState<string | null>(null);

  useEffect(() => {
    if (initialCase) markTermsAccepted();  // an existing conversation: the terms were accepted with it
    if (initialCase) chatHistory(initialCase).then(setMessages).catch((e) => setError(errorText(e)));
  }, [initialCase]);

  useEffect(() => setTts(canSpeak()), []);
  useEffect(() => {
    publicApi<{ daily_limit: number }>("/v1/chat/info").then((r) => setDailyLimit(r.daily_limit)).catch(() => {});
  }, []);
  // the «Чат» tab returns to the latest conversation
  useEffect(() => { if (caseId) try { localStorage.setItem(LAST_CASE_KEY, caseId); } catch {} }, [caseId]);

  const errText = useCallback((err: unknown) => {
    const key = err instanceof ApiError && err.code ? `chat.errors.${err.code}` : "";
    const limit = err instanceof ApiError && typeof err.detail === "object" && err.detail && "limit" in err.detail
      ? Number((err.detail as { limit: number }).limit) : dailyLimit;
    return key && t(key) !== key ? t(key, limit ? { limit } : undefined) : errorText(err);
  }, [t, dailyLimit]);

  async function openCase(text: string, skipTriage: boolean): Promise<string | null> {
    if (!skipTriage) {
      const tri = await publicApi<{ emergency: boolean; message: string; numbers: Emergency["numbers"] }>(
        "/v1/triage", { method: "POST", body: JSON.stringify({ text, country: "KZ", language: lang }) });
      if (tri.emergency) {
        setEmergency({ message: tri.message, numbers: tri.numbers, text });
        return null;
      }
    }
    const out = await api<{ case: CaseView; reply: Reply }>("/v1/cases", {
      // defer: the reply starts at once; the case's scenario is worked out on the server meanwhile
      method: "POST", body: JSON.stringify({ text, language: lang, country: "KZ", accept_terms: TERMS_VERSION, defer: true }),
    });
    setCaseId(out.case.id);
    markTermsAccepted();  // accepted with the first message: the line about the terms is not shown again
    window.history.replaceState(null, "", `/chat/${out.case.id}`);
    return out.case.id;
  }

  async function upload(id: string, list: Attached[]): Promise<Attached[]> {
    const done: Attached[] = [];
    for (const f of list) {
      if (f.id || !f.file) { done.push(f); continue; }
      const form = new FormData();
      form.append("file", f.file);
      form.append("kind", "other");
      const r = await api<{ evidence: { id: string } }>(`/v1/cases/${id}/evidence`, { method: "POST", body: form });
      done.push({ ...f, id: r.evidence.id, file: undefined });
    }
    return done;
  }

  async function send(textIn?: string, skipTriage = false, again?: Attached[]) {
    const text = (textIn ?? draft).trim();
    if (!text || busy) return;
    stopSpeaking();
    const list = again ?? files;
    // the message shows at once and the box empties, as in any messenger; the answer's dots follow right away
    const localId = `local-${Date.now()}`;
    setMessages((m) => [...m, { id: localId, role: "user", text, created_at: new Date().toISOString(),
      attachments: list.map((f) => ({ id: f.id ?? f.key, filename: f.filename })), norms: [] }]);
    if (!again) { setDraft(""); setFiles([]); }
    setBusy(true); setError(null); setEmergency(null); setFailed(null); setStreaming("");
    // set once the message reached the server: from then on a failure keeps it and offers «Повторить»
    let sent: Attached[] | null = null;
    let partial = "", answered = false, retry = true;
    const ctl = new AbortController();
    abort.current = ctl;
    const unsend = () => {  // nothing reached the server: the message goes back into the box
      setMessages((m) => m.filter((x) => x.id !== localId));
      if (!again) { setDraft(text); setFiles(list); }
    };
    try {
      const id = caseId ?? await openCase(text, skipTriage);
      if (!id) { unsend(); return; }
      const uploaded = await upload(id, list);
      const attachments = uploaded.filter((f) => f.id).map((f) => ({ id: f.id!, filename: f.filename }));
      sent = uploaded;
      await sendChat(id, text, attachments.map((a) => a.id), (ev) => {
        if (ev.type === "text") { partial += ev.text; setLookingUp(false); setStreaming((s) => (s ?? "") + ev.text); }
        else if (ev.type === "tool") setLookingUp(true);
        else if (ev.type === "error") setError(t(`chat.errors.${ev.code}`));
        else if (ev.type === "done") {
          answered = true;
          setMessages((m) => [...m, ev.message]);
          if (voiceMode) speak(ev.message.text, lang);
          if (typeof ev.remaining === "number" && ev.limit) setLeft({ n: ev.remaining, limit: ev.limit });
        }
      }, ctl.signal, lang);
    } catch (err) {
      if (ctl.signal.aborted) {  // stopped by the person: what was written stays, nothing to retry
        answered = true;
        if (partial.trim()) setMessages((m) => [...m, { id: `stopped-${Date.now()}`, role: "assistant", text: partial,
          created_at: new Date().toISOString(), attachments: [], norms: [] }]);
        return;
      }
      setError(errText(err));
      if (err instanceof ApiError && (err.code === "too_many_messages" || err.code === "agent_unavailable")) {
        retry = false;  // «Повторить» would not help
        if (err.code === "too_many_messages") setLeft((l) => ({ n: 0, limit: l?.limit ?? dailyLimit ?? 0 }));
      }
      if (!sent) unsend();
    } finally {
      if (sent && !answered && retry) setFailed({ partial, text, files: sent });
      setStreaming(null); setLookingUp(false); setBusy(false); abort.current = null;
    }
  }

  /** Send the message whose answer failed once more; its bubble is replaced, its files are not uploaded again. */
  function retryFailed() {
    if (!failed || busy) return;
    const { text, files: again } = failed;
    setMessages((m) => {
      const last = m[m.length - 1];
      return last && last.role === "user" && last.text === text ? m.slice(0, -1) : m;
    });
    send(text, true, again);
  }

  useEffect(() => {  // text typed on the home page arrives here and is sent once
    if (autoSend && initialDraft.trim() && !sentInitial.current) {
      sentInitial.current = true;
      send(initialDraft);
    }
  }, [autoSend, initialDraft]);

  // Examples for an empty chat: those of the chosen life situation (GET /v1/examples, which keeps them neutral),
  // else the hand-picked everyday tasks of the site's texts.
  const fallback = useMemo(() => {
    if (situation) return [1, 2, 3, 4].map((i) => t(`situations.${situation}.ex${i}`));
    const n = Number(t("helper.exampleCount")) || 0;
    return Array.from({ length: n }, (_, i) => t(`helper.examples.${i + 1}`)).slice(0, 4);
  }, [t, situation]);
  const [fromScenarios, setFromScenarios] = useState<string[]>([]);
  const empty = messages.length === 0 && streaming === null && !failed;
  useEffect(() => {
    if (!empty || !situation) return;  // without a chosen situation: the hand-picked everyday tasks
    const topics = SITUATIONS.find((s) => s.key === situation)?.topics ?? [];
    let live = true;
    publicApi<{ examples: string[] }>(`/v1/examples?${new URLSearchParams({ topics: topics.join(","), lang, limit: "4" })}`)
      .then((r) => { if (live) setFromScenarios(r.examples); }).catch(() => {});
    return () => { live = false; };
  }, [situation, lang, empty]);
  const examples = useMemo(
    () => [...fromScenarios, ...fallback.filter((e) => !fromScenarios.includes(e))].slice(0, 4),
    [fromScenarios, fallback]);

  // the document is offered under the latest reply that offers it, and only while nothing was said after it
  const last = messages[messages.length - 1];
  const offerId = streaming === null && last?.role === "assistant" && last.offer_document ? last.id : null;

  const links: MoreLink[] = [
    ...(caseId ? [{ href: `/case/${caseId}`, icon: "document" as IconName, label: `${t("chat.doc")} · ${t("chat.docPrice")}` }] : []),
    ...(LAWYERS_PUBLIC ? [{ href: "/lawyers", icon: "lawyer" as IconName, label: t("chat.lawyer") }] : []),
    { href: "/cases", icon: "briefcase", label: t("nav.cases") },
    { href: "/account", icon: "user", label: t("app.account") },
    { href: "/", icon: "home", label: t("app.home") },
    { href: caseId ? `/support?case=${caseId}` : "/support", icon: "mail", label: t("footer.support") },
    { href: "/terms", icon: "scroll", label: t("legal.terms") },
  ];
  const sections: MoreSection[] = [
    ...(tts ? [{ key: "voice", icon: "volume" as IconName, label: t("chat.voiceTitle"), render: () => (
      <button type="button" onClick={() => { setVoiceMode((v) => !v); stopSpeaking(); }} aria-pressed={voiceMode}
        className="flex min-h-12 w-full items-center justify-between gap-3 rounded-2xl border border-line px-4 text-sm font-medium">
        {voiceMode ? t("chat.voiceOn") : t("chat.voiceOff")}
        <span className={`h-6 w-10 rounded-full p-0.5 transition-colors ${voiceMode ? "bg-brand" : "bg-sand-deep"}`}>
          <span className={`block h-5 w-5 rounded-full bg-white transition-transform ${voiceMode ? "translate-x-4 rtl:-translate-x-4" : ""}`} />
        </span>
      </button>) }] : []),
    ...(caseId ? [{ key: "invite", icon: "share" as IconName, label: t("chat.share"), render: () => <Invite compact /> }] : []),
    { key: "about", icon: "info", label: t("app.about"), render: () => (
      <div className="space-y-3 text-sm">
        <p>{t("chat.free")}</p>
        <p className="text-muted">{t("legal.disclaimer")}</p>
      </div>) },
  ];

  const bar = (
    <div className="space-y-1.5">
      <Composer value={draft} setValue={setDraft} files={files} busy={busy} onSubmit={() => send()}
        onStop={streaming !== null ? () => abort.current?.abort() : undefined}
        placeholder={t("chat.placeholderNext")}
        onFiles={(fs) => setFiles((xs) => [...xs, ...fs.map((f, i) => ({ key: `${Date.now()}-${i}-${f.name}`, filename: f.name, file: f }))])}
        onRemove={(key) => setFiles((xs) => xs.filter((x) => x.key !== key))} />
      {left && left.limit > 0 && left.n <= REMAINING_FROM && (
        <p className="px-3 text-center text-xs text-muted">{t("chat.remaining", { n: left.n, limit: left.limit })}</p>
      )}
      {!caseId && empty && showTerms && (
        <p className="mx-auto max-w-sm px-4 text-center text-xs leading-relaxed text-muted [text-wrap:balance]">
          {t("legal.accept")}{" "}<Link href="/terms" className="link whitespace-nowrap">{t("legal.terms")}</Link>
        </p>
      )}
    </div>
  );

  return (
    <AppShell title={t("chat.brand")} subtitle={t("chat.subtitle")} back={caseId ? "/cases" : "/"} sections={sections} links={links} bar={bar} wallpaper
      avatar tabs={false} scrollKey={`${messages.length}-${streaming?.length ?? -1}-${!!error}-${!!failed}`}>
      <div className="space-y-1.5" aria-live="polite">

        {empty && (
          <div className="flex min-h-[55dvh] flex-col items-center justify-end gap-6 pb-2">
            <div className="space-y-4 text-center">
              <img src="/icons/icon-192.png" alt="" width={72} height={72} className="mx-auto rounded-full ring-1 ring-line" />
              <h2 className="text-[28px] font-semibold tracking-tight text-balance">{greeting(t)}</h2>
              {hint && <p className="mx-auto max-w-md text-[15px] text-muted">{hint}</p>}
            </div>
            {!draft.trim() && (
              <ul className="w-full space-y-2">
                {examples.map((e) => (
                  <li key={e}>
                    <button type="button" onClick={() => { setDraft(e); document.getElementById("chat-input")?.focus(); }}
                      className="flex min-h-14 w-full items-center gap-3 rounded-2xl bg-[var(--chat-in-bg)] px-4 py-3 text-start text-[17px] font-medium shadow-[var(--chat-shadow)] text-ink hover:bg-sand-deep">
                      <Icon name="chat" size={20} className="shrink-0 text-muted" />{e}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {!empty && (  // who the person is talking to, once at the top, as official chats do
          <p className="mx-auto max-w-md px-4 pt-2 pb-3 text-center text-xs leading-relaxed text-muted">{t("chat.notice")}</p>
        )}

        {messages.map((m, i) => {
          const day = i === 0 || dayOf(messages[i - 1].created_at) !== dayOf(m.created_at)
            ? <DayChip key={`d-${m.id}`} iso={m.created_at} /> : null;
          if (m.role === "user") {
            const seen = messages.slice(i + 1).some((x) => x.role === "assistant") || !m.id.startsWith("local-");
            return [day, (
              <Bubble key={m.id} mine at={m.created_at} seen={seen}>
                <p className="whitespace-pre-line">{m.text}</p>
                {m.attachments.map((a) => (
                  <p key={a.id} className="flex items-center gap-1.5 text-xs opacity-85"><Icon name="paperclip" size={14} />{a.filename}</p>
                ))}
              </Bubble>
            )];
          }
          return [day, (
            <Bubble key={m.id} mine={false} at={m.created_at}>
              <Reply text={m.text} />
              {m.norms.length > 0 && (
                <ul className="flex flex-wrap gap-1.5">
                  {m.norms.map((n) => (
                    <li key={`${n.act_code}-${n.article}`}>
                      <a href={n.url} target="_blank" rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 rounded-full bg-surface px-2.5 py-1 text-xs text-ink-soft hover:text-brand">
                        <Icon name="scroll" size={13} className="text-brand" />{t("chat.article", { n: n.article })} · {n.act}
                      </a>
                    </li>
                  ))}
                </ul>
              )}
              {m.id === offerId && caseId && (
                // an action inside the reply, as business chats do: one clear button
                <Link href={`/case/${caseId}`}
                  className="flex min-h-12 w-full flex-col items-center justify-center rounded-xl bg-[var(--chat-action-bg)] px-3 py-2 text-center hover:opacity-90">
                  <span className="font-semibold text-[var(--chat-accent)]">{t("chat.doc")}</span>
                </Link>
              )}
            </Bubble>
          )];
        })}

        {streaming !== null && (
          <Bubble mine={false}>
            {clean(streaming).replace(MORE_TAIL, "").trim() ? <Reply text={streaming} streaming /> : (
              <span className="flex items-center gap-2 text-muted">
                {lookingUp ? t("chat.lookingUp") : t("chat.thinking")}
                <span className="flex items-center gap-1" aria-hidden>
                  {[0, 1, 2].map((k) => (
                    <span key={k} className="h-1.5 w-1.5 rounded-full bg-muted motion-safe:animate-bounce" style={{ animationDelay: `${k * 150}ms` }} />
                  ))}
                </span>
              </span>
            )}
            <span className="sr-only" role="status">{t("chat.thinking")}</span>
          </Bubble>
        )}
        {failed && streaming === null && (
          <div className="space-y-2">
            {failed.partial && (
              <Bubble mine={false}>
                <Markdown text={clean(failed.partial).replace(MORE, "\n\n").replace(MORE_TAIL, "")} />
                <p className="text-xs text-muted">{t("chat.interrupted")}</p>
              </Bubble>
            )}
            <button type="button" onClick={retryFailed} disabled={busy}
              className="inline-flex min-h-10 items-center gap-1.5 rounded-full bg-[var(--chat-in-bg)] px-4 text-sm font-semibold shadow-[var(--chat-shadow)] hover:text-brand disabled:opacity-50">
              <Icon name="send" size={16} />{t("chat.retry")}
            </button>
          </div>
        )}
        {emergency && <EmergencyPanel info={emergency} onContinue={() => send(emergency.text, true)} />}
        {error && (  // a quiet line, as the messengers show a message that did not go
          <p role="alert" className="flex items-center justify-center gap-1.5 px-4 py-2 text-center text-[13px] text-danger">
            <Icon name="alert" size={15} className="shrink-0" />{error}
          </p>
        )}
      </div>
    </AppShell>
  );
}
