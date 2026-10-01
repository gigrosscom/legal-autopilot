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
  const [tools, setTools] = useState(false);  // «›» pressed while typing: attach and camera shown again
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

  useEffect(() => { if (!value) setTools(false); }, [value]);
  useEffect(() => {  // grow with the text, up to a limit
    const el = box.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, large ? 320 : 200)}px`;
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
  // «send» while recording: stop, then send what is in the box once the last words are written down
  const submit = () => {
    if (waiting) { sendAfter.current = true; if (dictation.listening) dictation.stop(); return; }
    if (!busy && hasText) onSubmit();
  };

  const attach = (
    <label title={t("chat.attach")}
      className={`flex shrink-0 cursor-pointer items-center justify-center rounded-full hover:bg-sand ${
        large ? "h-10 w-10 text-ink" : "h-11 w-10 text-[var(--chat-accent)]"} ${busy ? "pointer-events-none opacity-40" : ""}`}>
      <Icon name="plus" size={large ? 22 : 24} /><span className="sr-only">{t("chat.attach")}</span>
      <input type="file" multiple accept="image/*,application/pdf,text/plain,.doc,.docx" className="sr-only" disabled={busy}
        onChange={(e) => { const fs = Array.from(e.target.files ?? []); e.target.value = ""; if (fs.length) onFiles(fs); }} />
    </label>
  );
  // as in ChatGPT: the microphone and «send» side by side; send turns blue once there is something to send
  const micButton = dictation.transcribing ? (
    <span role="status" title={t("chat.transcribing")}
      className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-ink">
      <Icon name="spinner" size={20} /><span className="sr-only">{t("chat.transcribing")}</span>
    </span>
  ) : dictation.supported ? (
    <button type="button" onClick={dictation.listening ? dictation.stop : record} disabled={busy}
      aria-pressed={dictation.listening} title={dictation.listening ? t("chat.micStop") : t("chat.mic")}
      className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full ${dictation.listening
        ? "bg-danger text-white motion-safe:animate-pulse" : "text-ink hover:bg-sand"}`}>
      <Icon name={dictation.listening ? "stop" : "mic"} size={21} />
      <span className="sr-only">{dictation.listening ? t("chat.micStop") : t("chat.mic")}</span>
    </button>
  ) : null;
  const action = (
    <span className="flex shrink-0 items-center gap-1">
      {micButton}
      {onStop ? (
        <button type="button" onClick={onStop} title={t("chat.stop")}
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-ink text-white">
          <span className="h-3.5 w-3.5 rounded-[3px] bg-white" /><span className="sr-only">{t("chat.stop")}</span>
        </button>
      ) : (
      <button type="submit" disabled={busy || (!hasText && !dictation.listening) || dictation.transcribing} title={t("chat.send")}
        className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-action text-white transition-colors disabled:bg-sand-deep disabled:text-muted">
        <Icon name={busy ? "spinner" : "arrowUp"} size={20} /><span className="sr-only">{t("chat.send")}</span>
      </button>
      )}
    </span>
  );

  const filesList = files.length > 0 && (
    <ul className="flex flex-wrap gap-2 px-2 pt-1 pb-2">
      {files.map((f) => (
        <li key={f.key} className="inline-flex max-w-full items-center gap-1.5 rounded-full bg-sand py-1 ps-3 pe-1 text-xs">
          <Icon name="paperclip" size={14} className="shrink-0" /><span className="truncate">{f.filename}</span>
          <button type="button" aria-label={t("chat.remove")} onClick={() => onRemove(f.key)}
            className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-muted hover:bg-surface hover:text-ink">
            <Icon name="x" size={14} />
          </button>
        </li>
      ))}
    </ul>
  );
  // while recording: a red dot and the time, with «cancel»; the words themselves are in the box
  const recording = dictation.listening && (
    <span className="flex shrink-0 items-center gap-1.5">
      <button type="button" onClick={cancel} title={t("chat.cancel")}
        className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-ink hover:bg-sand">
        <Icon name="x" size={20} /><span className="sr-only">{t("chat.cancel")}</span>
      </button>
      <span className="flex items-center gap-1.5 pe-1 text-sm tabular-nums text-ink">
        <span aria-hidden className="h-2.5 w-2.5 rounded-full bg-danger motion-safe:animate-pulse" />
        <Elapsed since={dictation.startedAt} />
        <span role="status" className="sr-only">{t("chat.listening")}</span>
      </span>
    </span>
  );
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
        className={`block w-full flex-1 resize-none border-0 bg-transparent shadow-none outline-none placeholder:text-[#6b6b70] ${
          large ? "min-h-24 px-3 pt-2 text-[18px] leading-relaxed text-black" : "min-h-10 px-3 py-2 text-[18px] text-black"}`}
        style={{ outline: "none" }} /* the whole box shows focus */ />
    </>
  );
  const errorLine = dictation.error && (
    <p role="alert" className="px-3 pt-1 pb-1 text-xs text-danger">{t(`chat.errors.${dictation.error}`)}</p>
  );

  if (large) return (
    <form onSubmit={(e) => { e.preventDefault(); submit(); }}
      className="rounded-[28px] border border-line bg-surface p-3 shadow-[var(--shadow-raised)] transition-colors focus-within:border-ink/30">
      {filesList}
      <div className="space-y-2">
        {textarea}
        <div className="flex items-center justify-between">{recording || attach}{action}</div>
      </div>
      {errorLine}
    </form>
  );

  // The chat's box, as in WhatsApp: «+» · the message · camera · one round button (microphone, or send once
  // there is text, or stop while the answer is being written).
  const round = "flex h-11 w-11 shrink-0 items-center justify-center rounded-full";
  const main = dictation.listening ? (
    <span className="flex shrink-0 items-center">
      <button type="button" onClick={dictation.stop} title={t("chat.micStop")} className={`${round} text-[var(--chat-accent)] hover:bg-sand`}>
        <span className="h-3.5 w-3.5 rounded-[3px] bg-current" /><span className="sr-only">{t("chat.micStop")}</span>
      </button>
      <button type="submit" title={t("chat.send")} className={`${round} text-[var(--chat-accent)] hover:bg-sand`}>
        <Icon name="send" size={24} /><span className="sr-only">{t("chat.send")}</span>
      </button>
    </span>
  ) : onStop ? (
    <button type="button" onClick={onStop} title={t("chat.stop")} className={`${round} bg-ink text-white`}>
      <span className="h-3.5 w-3.5 rounded-[3px] bg-white" /><span className="sr-only">{t("chat.stop")}</span>
    </button>
  ) : dictation.transcribing ? (
    <span role="status" title={t("chat.transcribing")} className={`${round} text-[var(--chat-accent)]`}>
      <Icon name="spinner" size={22} /><span className="sr-only">{t("chat.transcribing")}</span>
    </span>
  ) : !hasText && dictation.supported ? (
    <button type="button" onClick={record} disabled={busy} title={t("chat.mic")} className={`${round} bg-[var(--chat-accent)] text-white`}>
      <Icon name="mic" size={21} /><span className="sr-only">{t("chat.mic")}</span>
    </button>
  ) : (
    // as in Messenger: a plain paper plane in the brand colour
    <button type="submit" disabled={busy || !hasText} title={t("chat.send")}
      className={`${round} text-[var(--chat-accent)] hover:bg-sand disabled:text-muted`}>
      <Icon name={busy ? "spinner" : "send"} size={24} /><span className="sr-only">{t("chat.send")}</span>
    </button>
  );
  const camera = (
    <label title={t("helper.photo")}
      className={`flex h-11 w-10 shrink-0 cursor-pointer items-center justify-center text-[var(--chat-accent)] ${busy ? "pointer-events-none opacity-40" : ""}`}>
      <Icon name="camera" size={23} /><span className="sr-only">{t("helper.photo")}</span>
      <input type="file" accept="image/*" capture="environment" className="sr-only" disabled={busy}
        onChange={(e) => { const fs = Array.from(e.target.files ?? []); e.target.value = ""; if (fs.length) onFiles(fs); }} />
    </label>
  );
  // While typing, the tools on the left fold into «›» so the message gets the width, as in Messenger.
  const folded = hasText && !tools;
  return (
    <form onSubmit={(e) => { e.preventDefault(); submit(); }}>
      {filesList}
      <div className="flex items-end gap-1">
        {dictation.listening ? recording : (folded ? (
          <button type="button" onClick={() => setTools(true)} title={t("chat.attach")}
            className="flex h-11 w-9 shrink-0 items-center justify-center text-[var(--chat-accent)]">
            <Icon name="chevronDown" size={22} className="-rotate-90 rtl:rotate-90" /><span className="sr-only">{t("chat.attach")}</span>
          </button>
        ) : <>{attach}{camera}</>)}
        <div className="flex min-h-11 min-w-0 flex-1 items-end rounded-[22px] bg-[var(--chat-field)] shadow-[var(--chat-shadow)]">
          {textarea}
        </div>
        {main}
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
