"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { LAST_CASE_KEY } from "@/components/AppNav";
import { AppShell, type MoreLink, type MoreSection } from "@/components/AppShell";
import { Mark } from "@/components/Brand";
import { EmergencyPanel } from "@/components/EmergencyPanel";
import { Invite } from "@/components/Invite";
import { Alert, Icon, type IconName } from "@/components/ui";
import { ApiError, api, errorText, publicApi, type CaseView, type Emergency, type Reply } from "@/lib/api";
import { chatHistory, sendChat, type ChatMessage } from "@/lib/chat";
import { LAWYERS_PUBLIC } from "@/lib/features";
import { useLang, useT } from "@/lib/i18n";
import { TERMS_VERSION } from "@/lib/legal/terms";
import { canSpeak, speak, stopSpeaking, useDictation } from "@/lib/voice";

type Pending = { key: string; filename: string; file?: File; id?: string };

/**
 * Free consultation as a chat: type or dictate, attach files, hear the answer. Without a case yet, the first
 * message runs the emergency check and opens the case; the chat then lives at /chat/<id>.
 */
export function Chat({ caseId: initialCase, draft: initialDraft = "", autoSend = false, hint }: {
  caseId: string | null; draft?: string; autoSend?: boolean; hint?: string;
}) {
  const t = useT();
  const { lang } = useLang();
  const [caseId, setCaseId] = useState(initialCase);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streaming, setStreaming] = useState<string | null>(null);
  const [lookingUp, setLookingUp] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [emergency, setEmergency] = useState<Emergency | null>(null);
  const [draft, setDraft] = useState(initialDraft);
  const [interim, setInterim] = useState("");
  const [files, setFiles] = useState<Pending[]>([]);
  const [voiceMode, setVoiceMode] = useState(false);
  const [speaking, setSpeaking] = useState<string | null>(null);
  const [tts, setTts] = useState(false);
  const box = useRef<HTMLTextAreaElement>(null);
  const sentInitial = useRef(false);

  const dictation = useDictation(lang, (fin, part) => {
    if (fin) setDraft((d) => (d ? `${d.trimEnd()} ${fin.trim()}` : fin.trim()));
    setInterim(part);
  });

  useEffect(() => {
    if (initialCase) chatHistory(initialCase).then(setMessages).catch((e) => setError(errorText(e)));
  }, [initialCase]);

  useEffect(() => setTts(canSpeak()), []);
  // the «Чат» tab returns to the latest conversation
  useEffect(() => { if (caseId) try { localStorage.setItem(LAST_CASE_KEY, caseId); } catch {} }, [caseId]);

  useEffect(() => {  // grow the box with the text, up to a limit
    const el = box.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [draft, interim]);

  const errText = useCallback((err: unknown) => {
    const key = err instanceof ApiError && err.code ? `chat.errors.${err.code}` : "";
    return key && t(key) !== key ? t(key) : errorText(err);
  }, [t]);

  async function openCase(text: string, skipTriage: boolean): Promise<string | null> {
    if (!skipTriage) {
      const tri = await publicApi<{ emergency: boolean; message: string; numbers: Emergency["numbers"] }>(
        "/v1/triage", { method: "POST", body: JSON.stringify({ text, country: "KZ", language: lang }) });
      if (tri.emergency) {
        setEmergency({ message: tri.message, numbers: tri.numbers });
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

  async function upload(id: string, list: Pending[]): Promise<Pending[]> {
    const done: Pending[] = [];
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

  async function send(textIn?: string, skipTriage = false) {
    const text = (textIn ?? draft).trim();
    if (!text || busy) return;
    if (dictation.listening) dictation.stop();
    stopSpeaking();
    setBusy(true); setError(null); setEmergency(null);
    try {
      const id = caseId ?? await openCase(text, skipTriage);
      if (!id) { setBusy(false); return; }
      const uploaded = await upload(id, files);
      const attachments = uploaded.filter((f) => f.id).map((f) => ({ id: f.id!, filename: f.filename }));
      setMessages((m) => [...m, { id: `local-${Date.now()}`, role: "user", text, created_at: new Date().toISOString(),
        attachments, norms: [] }]);
      setDraft(""); setInterim(""); setFiles([]);
      setStreaming("");
      await sendChat(id, text, attachments.map((a) => a.id), (ev) => {
        if (ev.type === "text") { setLookingUp(false); setStreaming((s) => (s ?? "") + ev.text); }
        else if (ev.type === "tool") setLookingUp(true);
        else if (ev.type === "error") setError(t(`chat.errors.${ev.code}`));
        else if (ev.type === "done") {
          setMessages((m) => [...m, ev.message]);
          if (voiceMode && speak(ev.message.text, lang)) setSpeaking(ev.message.id);
        }
      });
    } catch (err) {
      setError(errText(err));
    } finally {
      setStreaming(null); setLookingUp(false); setBusy(false);
    }
  }

  useEffect(() => {  // text typed on the home page arrives here and is sent once
    if (autoSend && initialDraft.trim() && !sentInitial.current) {
      sentInitial.current = true;
      send(initialDraft);
    }
  }, [autoSend, initialDraft]);

  const examples = useMemo(() => {
    const n = Number(t("helper.exampleCount")) || 0;
    return Array.from({ length: n }, (_, i) => t(`helper.examples.${i + 1}`)).slice(0, 4);
  }, [t]);

  const addFile = (f: File) => setFiles((xs) => [...xs, { key: `${Date.now()}-${f.name}`, filename: f.name, file: f }]);
  const toggleSpeak = (m: ChatMessage) => {
    if (speaking === m.id) { stopSpeaking(); setSpeaking(null); return; }
    if (speak(m.text, lang)) setSpeaking(m.id);
  };
  const empty = messages.length === 0 && streaming === null;

  const links: MoreLink[] = [
    ...(caseId ? [{ href: `/case/${caseId}`, icon: "document" as IconName, label: `${t("chat.doc")} · ${t("chat.docPrice")}` }] : []),
    ...(LAWYERS_PUBLIC ? [{ href: "/lawyers", icon: "lawyer" as IconName, label: t("chat.lawyer") }] : []),
    { href: "/cases", icon: "briefcase", label: t("nav.cases") },
    { href: "/account", icon: "user", label: t("app.account") },
    { href: "/", icon: "home", label: t("app.home") },
    { href: caseId ? `/support?case=${caseId}` : "/support", icon: "mail", label: t("footer.support") },
    { href: "/terms", icon: "scroll", label: t("legal.terms") },
  ];
  const sections: MoreSection[] = [{ key: "about", icon: "info", label: t("app.about"), render: () => (
    <div className="space-y-3 text-sm">
      <p>{t("chat.free")}</p>
      <p className="text-muted">{t("legal.disclaimer")}</p>
    </div>) }];

  const bar = (
    <div className="space-y-2">
        {files.length > 0 && (
          <ul className="flex flex-wrap gap-2">
            {files.map((f) => (
              <li key={f.key} className="inline-flex items-center gap-1.5 rounded-full bg-sand px-3 py-1 text-xs">
                <Icon name="paperclip" size={14} />{f.filename}
                <button type="button" aria-label={t("chat.remove")} onClick={() => setFiles((xs) => xs.filter((x) => x.key !== f.key))}
                  className="ms-1 text-muted hover:text-ink"><Icon name="x" size={14} /></button>
              </li>
            ))}
          </ul>
        )}
        <form onSubmit={(e) => { e.preventDefault(); send(); }}
          className="flex items-end gap-1 rounded-3xl border border-line bg-surface p-2 shadow-[var(--shadow-raised)] focus-within:border-accent">
          <label className={`flex h-10 w-10 shrink-0 cursor-pointer items-center justify-center rounded-full text-muted hover:bg-sand hover:text-ink ${busy ? "pointer-events-none opacity-50" : ""}`}
            title={t("chat.attach")}>
            <Icon name="paperclip" size={20} /><span className="sr-only">{t("chat.attach")}</span>
            <input type="file" accept="image/*,application/pdf,text/plain" className="sr-only" disabled={busy}
              onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) addFile(f); }} />
          </label>
          <label htmlFor="chat-input" className="sr-only">{t("chat.placeholder")}</label>
          <textarea id="chat-input" ref={box} rows={1} value={interim ? `${draft} ${interim}`.trim() : draft}
            onChange={(e) => { setDraft(e.target.value); setInterim(""); }}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send(); } }}
            placeholder={dictation.listening ? t("chat.listening") : t("chat.placeholder")} maxLength={4000}
            className="max-h-[200px] min-h-10 flex-1 resize-none border-0 bg-transparent px-2 py-2 shadow-none outline-none placeholder:text-muted"
            style={{ outline: "none" }} /* the whole box shows focus (focus-within) */ />
          {dictation.supported && (
            <button type="button" onClick={dictation.listening ? dictation.stop : dictation.start} disabled={busy}
              aria-pressed={dictation.listening} title={dictation.listening ? t("chat.micStop") : t("chat.mic")}
              className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full ${dictation.listening ? "bg-danger text-white motion-safe:animate-pulse" : "text-muted hover:bg-sand hover:text-ink"}`}>
              <Icon name={dictation.listening ? "stop" : "mic"} size={20} />
              <span className="sr-only">{dictation.listening ? t("chat.micStop") : t("chat.mic")}</span>
            </button>
          )}
          <button type="submit" disabled={busy || !(draft.trim() || interim.trim())} title={t("chat.send")}
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-ink text-white disabled:opacity-30">
            <Icon name={busy ? "spinner" : "arrowUp"} size={20} /><span className="sr-only">{t("chat.send")}</span>
          </button>
        </form>
        <div className="flex flex-wrap items-center justify-between gap-2 px-2 text-xs text-muted">
          <span>{t("chat.freeShort")}</span>
          {tts && (
            <button type="button" onClick={() => { setVoiceMode((v) => !v); stopSpeaking(); setSpeaking(null); }} aria-pressed={voiceMode}
              className="inline-flex min-h-8 items-center gap-1.5 hover:text-ink">
              <Icon name="volume" size={14} className={voiceMode ? "text-brand" : ""} />{voiceMode ? t("chat.voiceOn") : t("chat.voiceOff")}
            </button>
          )}
        </div>
        {!caseId && (
          <p className="px-2 text-xs text-muted">
            {t("legal.accept")} <Link href="/terms" className="link">{t("legal.terms")}</Link>
          </p>
        )}
    </div>
  );

  return (
    <AppShell title={t("app.chat")} subtitle="Konsiliér AI" back={caseId ? "/cases" : "/"} sections={sections}
      links={links} bar={bar} scrollKey={`${messages.length}-${streaming?.length ?? -1}-${!!error}`}>
      <div className="space-y-4" aria-live="polite">

        {empty && (
          <div className="space-y-4 py-6 sm:py-12">
            <Mark size={40} className="text-ink" />
            <p className="eyebrow">{t("chat.eyebrow")}</p>
            <h1 className="text-3xl font-semibold tracking-tight text-balance md:text-4xl">{t("chat.title")}</h1>
            <p className="max-w-xl text-muted">{hint ?? t("chat.lead")}</p>
            <div className="flex flex-wrap gap-2">
              {examples.map((e) => (
                <button key={e} type="button" onClick={() => setDraft(e)}
                  className="min-h-11 rounded-xl border border-line bg-surface px-4 py-2 text-start text-sm text-ink-soft hover:border-accent hover:bg-sand">{e}</button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m) => m.role === "user" ? (
          <div key={m.id} className="flex justify-end">
            <div className="max-w-[85%] space-y-2 rounded-2xl rounded-ee-md bg-sand-deep px-4 py-2.5 text-ink">
              <p className="whitespace-pre-line">{m.text}</p>
              {m.attachments.map((a) => (
                <p key={a.id} className="flex items-center gap-1.5 text-xs opacity-90"><Icon name="paperclip" size={14} />{a.filename}</p>
              ))}
            </div>
          </div>
        ) : (
          <div key={m.id} className="space-y-2">
            <p className="flex items-center gap-2 text-sm font-semibold text-ink"><Mark size={18} />Konsiliér AI</p>
            <div className="min-w-0 space-y-2 lg:ps-7">
              <p className="whitespace-pre-line text-[16px] leading-[1.7]">{m.text}</p>
              {m.norms.length > 0 && (
                <ul className="flex flex-wrap gap-2">
                  {m.norms.map((n) => (
                    <li key={`${n.act_code}-${n.article}`}>
                      <a href={n.url} target="_blank" rel="noopener noreferrer"
                        className="inline-flex items-center gap-1.5 rounded-full border border-line bg-surface px-3 py-1 text-xs hover:border-brand">
                        <Icon name="shieldCheck" size={14} className="text-brand" />{t("chat.article", { n: n.article })} · {n.act}
                      </a>
                    </li>
                  ))}
                </ul>
              )}
              {tts && (
                <button type="button" onClick={() => toggleSpeak(m)} className="inline-flex min-h-8 items-center gap-1.5 text-xs text-muted hover:text-ink">
                  <Icon name={speaking === m.id ? "stop" : "volume"} size={14} />{speaking === m.id ? t("chat.stopSpeak") : t("chat.speak")}
                </button>
              )}
            </div>
          </div>
        ))}

        {streaming !== null && (
          <div className="space-y-2">
            <p className="flex items-center gap-2 text-sm font-semibold text-ink"><Mark size={18} />Konsiliér AI</p>
            <div className="min-w-0 lg:ps-7">
              {streaming && <p className="whitespace-pre-line text-[16px] leading-[1.7]">{streaming}</p>}
              <p className="flex items-center gap-2 text-sm text-muted" role="status">
                <Icon name="spinner" size={14} />{lookingUp ? t("chat.lookingUp") : t("chat.thinking")}
              </p>
            </div>
          </div>
        )}
        {emergency && <EmergencyPanel info={emergency} onContinue={() => send(undefined, true)} />}
        {error && <Alert tone="danger" role="alert">{error}</Alert>}

        {caseId && messages.length > 0 && streaming === null && (
          <div className="grid gap-2 sm:grid-cols-2">
            <Link href={`/case/${caseId}`} className="flex min-h-14 items-center gap-3 rounded-2xl border border-line bg-surface px-4 hover:border-brand">
              <Icon name="document" size={22} className="text-brand" />
              <span className="flex-1"><span className="block font-semibold">{t("chat.doc")}</span><span className="text-xs text-muted">{t("chat.docPrice")}</span></span>
            </Link>
            {LAWYERS_PUBLIC && <Link href="/lawyers" className="flex min-h-14 items-center gap-3 rounded-2xl border border-line bg-surface px-4 hover:border-brand">
              <Icon name="lawyer" size={22} className="text-brand" />
              <span className="flex-1"><span className="block font-semibold">{t("chat.lawyer")}</span><span className="text-xs text-muted">{t("chat.lawyerPrice")}</span></span>
            </Link>}
          </div>
        )}
        {caseId && messages.some((m) => m.role !== "user") && streaming === null && <Invite compact />}
      </div>
    </AppShell>
  );
}
