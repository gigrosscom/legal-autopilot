"use client";

import { useEffect, useRef, useState, type Dispatch, type SetStateAction } from "react";
import { Icon } from "@/components/ui";
import { useLang, useT } from "@/lib/i18n";
import { useVoiceInput } from "@/lib/voice";

export type Attached = { key: string; filename: string; file?: File; id?: string };

/**
 * The message box, as in ChatGPT: attach (photos, PDF, documents — several at once, the camera on phones), the text
 * grows with what is typed, the microphone and «send» side by side. While recording, the box shows a wave with
 * «cancel», «stop» (the words go into the box) and «send» (sent as soon as they are written down). `large` is the
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
  const [interim, setInterim] = useState("");
  const box = useRef<HTMLTextAreaElement>(null);
  const discard = useRef(false);     // «cancel»: what is still being recognised is dropped
  const sendAfter = useRef(false);   // «send» while recording: sent once the words are in the box
  const before = useRef("");         // the box as it was when recording started
  const dictation = useVoiceInput(lang, (fin, part) => {
    if (discard.current) return;
    if (fin) setValue((d) => (d ? `${d.trimEnd()} ${fin.trim()}` : fin.trim()));
    setInterim(part);
  });
  const shown = interim ? `${value} ${interim}`.trim() : value;
  const hasText = shown.trim().length > 0;

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
    setInterim("");
    if (value.trim() && !busy) onSubmit();
  }, [waiting, value, busy, onSubmit]);
  const record = () => { discard.current = false; sendAfter.current = false; before.current = value; dictation.start(); };
  const cancel = () => { discard.current = true; sendAfter.current = false; dictation.stop(); setValue(before.current); setInterim(""); };
  const sendNow = () => { sendAfter.current = true; if (dictation.listening) dictation.stop(); };
  const submit = () => {
    if (waiting) { if (dictation.listening) dictation.stop(); return; }
    setInterim("");
    if (!busy && hasText) onSubmit();
  };

  const attach = (
    <label title={t("chat.attach")}
      className={`flex h-10 w-10 shrink-0 cursor-pointer items-center justify-center rounded-full text-ink hover:bg-sand ${busy ? "pointer-events-none opacity-40" : ""}`}>
      <Icon name="plus" size={22} /><span className="sr-only">{t("chat.attach")}</span>
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
      <button type="submit" disabled={busy || !hasText || dictation.transcribing} title={t("chat.send")}
        className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-action text-white transition-colors disabled:bg-sand-deep disabled:text-muted">
        <Icon name={busy ? "spinner" : "arrowUp"} size={20} /><span className="sr-only">{t("chat.send")}</span>
      </button>
      )}
    </span>
  );

  return (
    <form onSubmit={(e) => { e.preventDefault(); submit(); }}
      className={`border border-line bg-surface shadow-[var(--shadow-raised)] transition-colors focus-within:border-ink/30 ${
        large ? "rounded-[28px] p-3" : "rounded-[26px] p-1.5"}`}>
      {files.length > 0 && (
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
      )}
      {dictation.listening ? (
        <div className={`flex items-center gap-2 ${large ? "min-h-[7.5rem] px-1" : ""}`}>
          <button type="button" onClick={cancel} title={t("chat.cancel")}
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-sand text-ink hover:bg-sand-deep">
            <Icon name="x" size={20} /><span className="sr-only">{t("chat.cancel")}</span>
          </button>
          <span className="flex h-10 min-w-0 flex-1 items-center justify-center gap-[3px] overflow-hidden" role="status"
            aria-label={t("chat.listening")}>
            {Array.from({ length: 28 }, (_, i) => (
              <span key={i} className="wave-bar h-6 w-[3px] shrink-0 rounded-full bg-ink/70"
                style={{ animationDelay: `${(i * 97) % 900}ms` }} />
            ))}
          </span>
          <button type="button" onClick={dictation.stop} title={t("chat.micStop")}
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-sand text-ink hover:bg-sand-deep">
            <span className="h-3.5 w-3.5 rounded-[3px] bg-ink" /><span className="sr-only">{t("chat.micStop")}</span>
          </button>
          <button type="button" onClick={sendNow} title={t("chat.send")}
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-action text-white">
            <Icon name="arrowUp" size={20} /><span className="sr-only">{t("chat.send")}</span>
          </button>
        </div>
      ) : (
      <div className={large ? "space-y-2" : "flex items-end gap-1"}>
        {!large && attach}
        <label htmlFor={large ? "home-input" : "chat-input"} className="sr-only">{placeholder}</label>
        <textarea id={large ? "home-input" : "chat-input"} ref={box} rows={large ? 3 : 1} value={shown}
          onChange={(e) => { setValue(e.target.value); setInterim(""); }}
          onKeyDown={(e) => {
            // Enter sends on a computer; on a phone it is a new line, as in the messengers
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing && matchMedia("(pointer: fine)").matches) {
              e.preventDefault(); submit();
            }
          }}
          placeholder={dictation.transcribing ? t("chat.transcribing") : dictation.listening ? t("chat.listening") : placeholder}
          maxLength={4000}
          className={`block w-full flex-1 resize-none border-0 bg-transparent shadow-none outline-none placeholder:text-muted ${
            large ? "min-h-24 px-3 pt-2 text-[17px] leading-relaxed" : "min-h-10 px-2 py-2 text-[16px]"}`}
          style={{ outline: "none" }} /* the whole box shows focus */ />
        {large ? <div className="flex items-center justify-between">{attach}{action}</div> : action}
      </div>
      )}
      {dictation.error && (
        <p role="alert" className="px-3 pt-1 pb-1 text-xs text-danger">{t(`chat.errors.${dictation.error}`)}</p>
      )}
    </form>
  );
}
