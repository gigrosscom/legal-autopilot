"use client";

import { useEffect, useRef, useState, type Dispatch, type SetStateAction } from "react";
import { Icon } from "@/components/ui";
import { useLang, useT } from "@/lib/i18n";
import { joinText, useVoiceInput } from "@/lib/voice";

export type Attached = { key: string; filename: string; file?: File; id?: string };

/**
 * The message box, as in ChatGPT: attach (photos, PDF, documents — several at once, the camera on phones), the text
 * grows with what is typed, the microphone and «send» side by side. While recording, the words appear in the box as
 * they are said (after what was already typed), with a red dot and a timer, «cancel», «stop» and «send»; after
 * «stop» the text stays in the box to be corrected, and only «send» sends it. `large` is the
 * home page's version: more room to describe the situation.
 */
export function Composer({ value, setValue, files, onFiles, onRemove, onSubmit, onStop, busy = false, placeholder,
  large = false, autoFocus = false }: {
  value: string; setValue: Dispatch<SetStateAction<string>>;
  files: Attached[]; onFiles: (fs: File[]) => void; onRemove: (key: string) => void;
  onSubmit: () => void; busy?: boolean;
  onStop?: () => void;  // the answer is being written: the send button becomes «Стоп»
  placeholder: string; large?: boolean; autoFocus?: boolean;
}) {
  const t = useT();
  const { lang } = useLang();
  const box = useRef<HTMLTextAreaElement>(null);
  const discard = useRef(false);     // «cancel»: what is still being recognised is dropped
  const sendAfter = useRef(false);   // «send» while recording: sent once the words are in the box
  const before = useRef("");         // the box as it was when recording started
  const typed = useRef(false);       // the person edited the box while recording: their edit wins
  const dictation = useVoiceInput(lang, (said) => {
    if (discard.current || typed.current) return;
    setValue(joinText(before.current, said));  // live: interim words included, after what was typed
  });
  const shown = value;
  const hasText = shown.trim().length > 0;

  useEffect(() => {  // grow with the text, up to a limit
    const el = box.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, large ? 320 : 240)}px`;
  }, [shown, large]);
  useEffect(() => { if (autoFocus && matchMedia("(pointer: fine)").matches) box.current?.focus(); }, [autoFocus]);

  // while a recording is still being turned into text, sending waits for it
  const waiting = dictation.listening || dictation.transcribing;
  useEffect(() => {
    if (waiting || !sendAfter.current) return;
    sendAfter.current = false;
    if (value.trim() && !busy) onSubmit();
  }, [waiting, value, busy, onSubmit]);
  const record = () => {
    discard.current = false; typed.current = false; sendAfter.current = false; before.current = value; dictation.start();
  };
  const cancel = () => { discard.current = true; sendAfter.current = false; dictation.stop(); setValue(before.current); };
  // «■»: stop and keep the words in the box to be corrected — the cursor at the end, the keyboard may stay open
  const refocus = useRef(false);
  const focusEnd = () => {
    const el = box.current;
    if (el) { el.focus(); requestAnimationFrame(() => { el.selectionStart = el.selectionEnd = el.value.length; }); }
  };
  const stopKeep = () => { refocus.current = true; dictation.stop(); focusEnd(); };
  // the chat's box is laid out anew once recording ends: give it the focus back, cursor after the last word
  useEffect(() => { if (!waiting && refocus.current) { refocus.current = false; focusEnd(); } }, [waiting]);
  // «send» while recording: stop, then send what is in the box once the last words are written down
  const submit = () => {
    if (waiting) { sendAfter.current = true; if (dictation.listening) dictation.stop(); return; }
    if (!busy && hasText) onSubmit();
  };

  // Controls sit in their own row UNDER the field, as in the Claude / ChatGPT apps: attach (and the camera in the
  // chat) on the left, microphone and send on the right. The message gets the full width on the row above them.
  const round = "flex h-11 w-11 shrink-0 items-center justify-center rounded-full transition-colors";
  const attach = (
    <label title={t("chat.attach")}
      className={`${round} cursor-pointer text-ink hover:bg-sand-deep ${busy ? "pointer-events-none opacity-40" : ""}`}>
      <Icon name="plus" size={24} /><span className="sr-only">{t("chat.attach")}</span>
      <input type="file" multiple accept="image/*,application/pdf,text/plain,.doc,.docx" className="sr-only" disabled={busy}
        onChange={(e) => { const fs = Array.from(e.target.files ?? []); e.target.value = ""; if (fs.length) onFiles(fs); }} />
    </label>
  );
  const camera = (
    <label title={t("helper.photo")}
      className={`${round} cursor-pointer text-ink hover:bg-sand-deep ${busy ? "pointer-events-none opacity-40" : ""}`}>
      <Icon name="camera" size={23} /><span className="sr-only">{t("helper.photo")}</span>
      <input type="file" accept="image/*" capture="environment" className="sr-only" disabled={busy}
        onChange={(e) => { const fs = Array.from(e.target.files ?? []); e.target.value = ""; if (fs.length) onFiles(fs); }} />
    </label>
  );
  // microphone: idle → neutral; recording → red and pulsing; turning speech into text → a spinner
  const micButton = dictation.transcribing ? (
    <span role="status" title={t("chat.transcribing")} className={`${round} text-ink`}>
      <Icon name="spinner" size={20} /><span className="sr-only">{t("chat.transcribing")}</span>
    </span>
  ) : dictation.supported ? (
    <button type="button" onClick={dictation.listening ? dictation.stop : record} disabled={busy}
      aria-pressed={dictation.listening} title={dictation.listening ? t("chat.micStop") : t("chat.mic")}
      className={`${round} ${dictation.listening
        ? "bg-danger-strong text-white motion-safe:animate-pulse" : "text-ink hover:bg-sand-deep"}`}>
      <Icon name={dictation.listening ? "stop" : "mic"} size={21} />
      <span className="sr-only">{dictation.listening ? t("chat.micStop") : t("chat.mic")}</span>
    </button>
  ) : null;
  // send: a solid round button in the brand colour with an up arrow, as in the Claude / ChatGPT apps;
  // while the answer is being written it turns into «Стоп» (a square).
  const sendButton = onStop ? (
    <button type="button" onClick={onStop} title={t("chat.stop")} className={`${round} bg-ink text-surface`}>
      <span className="h-3.5 w-3.5 rounded-[3px] bg-current" /><span className="sr-only">{t("chat.stop")}</span>
    </button>
  ) : (
    <button type="submit" disabled={busy || (!hasText && !dictation.listening) || dictation.transcribing} title={t("chat.send")}
      className={`${round} bg-action text-white disabled:bg-sand-deep disabled:text-muted`}>
      <Icon name={busy ? "spinner" : "arrowUp"} size={20} /><span className="sr-only">{t("chat.send")}</span>
    </button>
  );
  const controlsRow = (
    <div className="flex items-center justify-between gap-2">
      <span className="flex items-center gap-0.5">{attach}{!large && camera}</span>
      <span className="flex items-center gap-1.5">{!onStop && micButton}{sendButton}</span>
    </div>
  );

  const filesList = files.length > 0 && (
    <ul className="flex flex-wrap gap-2 px-1 pt-1 pb-2">
      {files.map((f) => (
        <li key={f.key} className="inline-flex max-w-full items-center gap-1.5 rounded-full bg-sand-deep py-1 ps-3 pe-1 text-xs">
          <Icon name="paperclip" size={14} className="shrink-0" /><span className="truncate">{f.filename}</span>
          <button type="button" aria-label={t("chat.remove")} onClick={() => onRemove(f.key)}
            className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-muted hover:bg-surface hover:text-ink">
            <Icon name="x" size={14} />
          </button>
        </li>
      ))}
    </ul>
  );
  // Big, crisp text as in the Claude app (owner, decisions.md 03.10): ≥ 20 px, roomy line-height, near-black ink in
  // the light theme and near-white in the dark, placeholder no fainter than --color-muted. Never faint or small.
  const textarea = (
    <>
      <label htmlFor={large ? "home-input" : "chat-input"} className="sr-only">{placeholder}</label>
      <textarea id={large ? "home-input" : "chat-input"} ref={box} rows={large ? 3 : 1} value={shown}
        onChange={(e) => {
          setValue(e.target.value);
          // typing while recording: the edit is kept and the recording stops (the next words would overwrite it)
          if (dictation.listening) { typed.current = true; dictation.stop(); }
        }}
        onKeyDown={(e) => {
          // Enter sends on a computer; on a phone it is a new line, as in the messengers
          if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing && matchMedia("(pointer: fine)").matches) {
            e.preventDefault(); submit();
          }
        }}
        placeholder={dictation.transcribing ? t("chat.transcribing") : dictation.listening ? t("chat.listening") : placeholder}
        maxLength={4000}
        className={`block w-full resize-none border-0 bg-transparent px-2 pt-1 pb-1 text-[20px] leading-[1.4] text-ink shadow-none outline-none placeholder:text-muted ${
          large ? "min-h-[84px]" : "min-h-9"}`}
        style={{ outline: "none" }} /* the whole box shows focus */ />
    </>
  );
  // Recording, as in the Claude app (owner's sample 02.10): the words grow in the box above, and one row below —
  // «✕» (cancel) · the loudness wave · «■» (stop, keep the text to correct) · «↑» (send now)
  const ctl = "flex h-11 w-11 shrink-0 items-center justify-center rounded-full";
  const recordingRow = waiting && (
    <div className="flex items-center gap-2">
      <button type="button" onClick={cancel} title={t("chat.cancel")} className={`${ctl} bg-surface text-ink ring-1 ring-line hover:bg-sand-deep`}>
        <Icon name="x" size={20} /><span className="sr-only">{t("chat.cancel")}</span>
      </button>
      <div className="flex min-w-0 flex-1 items-center justify-center gap-2">
        {dictation.transcribing
          ? <span role="status" className="flex items-center gap-2 text-sm text-muted"><Icon name="spinner" size={18} />{t("chat.transcribing")}</span>
          : <>
              <Wave levels={dictation.levels} />
              <span className="shrink-0 text-xs tabular-nums text-muted"><Elapsed since={dictation.startedAt} /></span>
              <span role="status" className="sr-only">{t("chat.listening")}</span>
            </>}
      </div>
      <button type="button" onClick={stopKeep} disabled={!dictation.listening} title={t("chat.micStop")}
        className={`${ctl} bg-surface text-ink ring-1 ring-line hover:bg-sand-deep disabled:opacity-40`}>
        <span className="h-3.5 w-3.5 rounded-[3px] bg-current" /><span className="sr-only">{t("chat.micStop")}</span>
      </button>
      <button type="submit" title={t("chat.send")} className={`${ctl} bg-action text-white`}>
        <Icon name="arrowUp" size={20} /><span className="sr-only">{t("chat.send")}</span>
      </button>
    </div>
  );
  const errorLine = dictation.error && (
    <p role="alert" className="px-3 pt-1 pb-1 text-xs text-danger">{t(`chat.errors.${dictation.error}`)}</p>
  );

  // One roomy panel for both the home page and the chat, in the Claude style: a soft filled field with big rounded
  // corners and air top and bottom, the message on its own line, the controls on a row underneath.
  const shell = `rounded-[24px] border border-line bg-[var(--chat-field)] px-2.5 pt-3 pb-2 transition-colors focus-within:border-ink/25${
    large ? " shadow-[var(--shadow-raised)]" : ""}`;
  return (
    <form onSubmit={(e) => { e.preventDefault(); submit(); }}>
      <div className={shell}>
        {filesList}
        {textarea}
        <div className="mt-1.5">{recordingRow || controlsRow}</div>
      </div>
      {errorLine}
    </form>
  );
}

/** Time since `since` as m:ss, ticking every second (hidden from screen readers: it would be read out each second). */
function Elapsed({ since }: { since: number }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);
  const s = Math.max(0, Math.floor((now - (since || now)) / 1000));
  return <span aria-hidden>{`${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`}</span>;
}

/** The loudness wave while recording: quiet moments are dots, speech rises as bars (newest on the right). Without a
 *  level (the browser's own recognition) the bars just breathe. */
function Wave({ levels }: { levels: number[] }) {
  const n = 28;
  const pts = levels.length ? [...Array(Math.max(0, n - levels.length)).fill(0), ...levels].slice(-n) : null;
  return (
    <span aria-hidden className="flex h-7 min-w-0 flex-1 items-center justify-center gap-[3px] overflow-hidden">
      {Array.from({ length: n }, (_, i) => {
        const v = pts ? pts[i] : null;
        return v === null
          ? <span key={i} className="voice-bar w-[3px] rounded-full bg-action" style={{ animationDelay: `${(i % 7) * 110}ms` }} />
          : <span key={i} className="w-[3px] rounded-full bg-action transition-[height] duration-75"
              style={{ height: `${Math.max(3, Math.round(v * 28))}px`, opacity: v < 0.08 ? 0.45 : 1 }} />;
      })}
    </span>
  );
}
