"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { LAST_CASE_KEY } from "@/components/AppNav";
import { AppShell, type MoreLink, type MoreSection } from "@/components/AppShell";
import { Composer, type Attached } from "@/components/Composer";
import { EmergencyPanel } from "@/components/EmergencyPanel";
import { Invite } from "@/components/Invite";
import { Alert, Icon, type IconName } from "@/components/ui";
import { ApiError, api, errorText, publicApi, type CaseView, type Emergency, type Reply } from "@/lib/api";
import { chatHistory, sendChat, type ChatMessage } from "@/lib/chat";
import { LAWYERS_PUBLIC } from "@/lib/features";
import { useLang, useT } from "@/lib/i18n";
import { TERMS_VERSION } from "@/lib/legal/terms";
import { SITUATIONS } from "@/lib/situations";
import { canSpeak, speak, stopSpeaking } from "@/lib/voice";

/** The count of free messages left shows once this many or fewer remain (e.g. after the 30th of 40). */
const REMAINING_FROM = 10;
/** The marker a reply ends with when it offers a document; hidden while the reply streams in. */
const OFFER = /\[?\[\s*DOC[A-Z]*\s*\]?\]?\s*$|\[\[?\s*$/;
const clean = (text: string) => text.replace(OFFER, "").trimEnd();

const BUBBLE = "max-w-[88%] rounded-[20px] px-4 py-2.5 text-[16px] leading-[1.55] sm:max-w-[80%]";

/** Konsiliér's side of the dialogue. */
function Reply({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex justify-start">
      <div className={`${BUBBLE} min-w-0 space-y-2 rounded-es-md bg-sand text-ink`}>{children}</div>
    </div>
  );
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

  useEffect(() => {
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
      method: "POST", body: JSON.stringify({ text, language: lang, country: "KZ", accept_terms: TERMS_VERSION }),
    });
    setCaseId(out.case.id);
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
      });
    } catch (err) {
      setError(errText(err));
      if (err instanceof ApiError && (err.code === "too_many_messages" || err.code === "agent_unavailable")) {
        retry = false;  // «Повторить» would not help
        if (err.code === "too_many_messages") setLeft((l) => ({ n: 0, limit: l?.limit ?? dailyLimit ?? 0 }));
      }
      if (!sent) unsend();
    } finally {
      if (sent && !answered && retry) setFailed({ partial, text, files: sent });
      setStreaming(null); setLookingUp(false); setBusy(false);
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

  // Examples for an empty chat: those of the chosen life situation, else everyday ones (GET /v1/examples, which
  // keeps them neutral); the site's texts fill in where a language has none yet.
  const fallback = useMemo(() => {
    if (situation) return [1, 2, 3, 4].map((i) => t(`situations.${situation}.ex${i}`));
    const n = Number(t("helper.exampleCount")) || 0;
    return Array.from({ length: n }, (_, i) => t(`helper.examples.${i + 1}`)).slice(0, 4);
  }, [t, situation]);
  const [fromScenarios, setFromScenarios] = useState<string[]>([]);
  const empty = messages.length === 0 && streaming === null && !failed;
  useEffect(() => {
    if (!empty) return;
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
        placeholder={empty ? t("chat.placeholder") : t("chat.placeholderNext")}
        onFiles={(fs) => setFiles((xs) => [...xs, ...fs.map((f, i) => ({ key: `${Date.now()}-${i}-${f.name}`, filename: f.name, file: f }))])}
        onRemove={(key) => setFiles((xs) => xs.filter((x) => x.key !== key))} />
      {left && left.limit > 0 && left.n <= REMAINING_FROM && (
        <p className="px-3 text-center text-xs text-muted">{t("chat.remaining", { n: left.n, limit: left.limit })}</p>
      )}
      {!caseId && empty && (
        <p className="px-3 text-center text-xs text-muted">
          {t("legal.accept")} <Link href="/terms" className="link">{t("legal.terms")}</Link>
        </p>
      )}
    </div>
  );

  return (
    <AppShell title={t("chat.brand")} back={caseId ? "/cases" : "/"} sections={sections}
      links={links} bar={bar} scrollKey={`${messages.length}-${streaming?.length ?? -1}-${!!error}-${!!failed}`}>
      <div className="space-y-2.5" aria-live="polite">

        {empty && (
          <div className="flex min-h-[45dvh] flex-col items-center justify-end gap-5 pb-4 text-center">
            <div className="space-y-2">
              <h2 className="text-2xl font-semibold tracking-tight text-balance md:text-3xl">{t("chat.title")}</h2>
              <p className="mx-auto max-w-md text-[15px] text-muted">{hint ?? t("chat.lead")}</p>
            </div>
            {!draft.trim() && (
              <ul className="flex flex-wrap justify-center gap-2">
                {examples.map((e) => (
                  <li key={e}>
                    <button type="button" onClick={() => { setDraft(e); document.getElementById("chat-input")?.focus(); }}
                      className="min-h-10 rounded-full border border-line bg-surface px-4 py-2 text-start text-sm text-ink hover:bg-sand">{e}</button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {messages.map((m) => m.role === "user" ? (
          <div key={m.id} className="flex justify-end">
            <div className={`${BUBBLE} space-y-1.5 rounded-ee-md bg-brand text-white`}>
              <p className="whitespace-pre-line">{m.text}</p>
              {m.attachments.map((a) => (
                <p key={a.id} className="flex items-center gap-1.5 text-xs text-white/85"><Icon name="paperclip" size={14} />{a.filename}</p>
              ))}
            </div>
          </div>
        ) : (
          <Reply key={m.id}>
            <p className="whitespace-pre-line">{clean(m.text)}</p>
            {m.norms.length > 0 && (
              <ul className="flex flex-wrap gap-1.5 pt-0.5">
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
              <Link href={`/case/${caseId}`}
                className="mt-1 flex min-h-12 items-center gap-3 rounded-2xl bg-surface px-3.5 py-2 hover:ring-1 hover:ring-brand">
                <Icon name="document" size={20} className="shrink-0 text-brand" />
                <span className="flex-1 font-semibold">{t("chat.doc")}</span>
                <span className="text-sm text-muted">{t("chat.docPrice")}</span>
              </Link>
            )}
          </Reply>
        ))}

        {streaming !== null && (
          <Reply>
            {clean(streaming) ? <p className="whitespace-pre-line">{clean(streaming)}</p> : (
              <span className="flex h-6 items-center gap-1" aria-hidden>
                {[0, 1, 2].map((i) => (
                  <span key={i} className="h-2 w-2 rounded-full bg-muted motion-safe:animate-bounce" style={{ animationDelay: `${i * 150}ms` }} />
                ))}
              </span>
            )}
            <span className="sr-only" role="status">{t("chat.thinking")}</span>
            {lookingUp && <p className="flex items-center gap-2 text-xs text-muted"><Icon name="spinner" size={12} />{t("chat.lookingUp")}</p>}
          </Reply>
        )}
        {failed && streaming === null && (
          <div className="space-y-2">
            {failed.partial && (
              <Reply>
                <p className="whitespace-pre-line">{clean(failed.partial)}</p>
                <p className="text-xs text-muted">{t("chat.interrupted")}</p>
              </Reply>
            )}
            <button type="button" onClick={retryFailed} disabled={busy}
              className="inline-flex min-h-10 items-center gap-1.5 rounded-full border border-line bg-surface px-4 text-sm font-semibold hover:border-brand disabled:opacity-50">
              <Icon name="send" size={16} />{t("chat.retry")}
            </button>
          </div>
        )}
        {emergency && <EmergencyPanel info={emergency} onContinue={() => send(emergency.text, true)} />}
        {error && <Alert tone="danger" role="alert">{error}</Alert>}
      </div>
    </AppShell>
  );
}
