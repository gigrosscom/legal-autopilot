"use client";

import { useEffect, useRef, useState } from "react";
import { Icon } from "@/components/ui";
import { DOC_ACCEPT } from "@/components/FilePicker";
import type { Question } from "@/lib/api";
import { useT } from "@/lib/i18n";

const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
/** "^\\d{12}$" → 12: fields made of digits only get the digit keypad and a length counter. */
const digitsOnly = (pattern?: string | null): number | null => {
  const m = pattern?.match(/^\^?\\d\{(\d+)\}\$?$/);
  return m ? Number(m[1]) : null;
};
const groupDigits = (digits: string) => digits.replace(/\B(?=(\d{3})+(?!\d))/g, " ");

/**
 * The bottom input of the case screen, shaped by the question: a calendar for dates, a digit keypad with
 * thousands grouping for sums, the phone / e-mail keyboards, photo and file buttons for documents, and a free
 * text box when no specific question is asked. Sends a value the server already understands.
 */
export function AnswerBar({ question, busy, currency, onSend, onFiles, onSkip, onDone, placeholder }: {
  question: Question | null; busy: boolean; currency?: string | null;
  onSend: (text: string, shown?: string) => Promise<boolean> | void; onFiles: (fs: File[]) => void; onSkip: () => void; onDone: () => void;
  placeholder?: string;
}) {
  const t = useT();
  const type = question?.type ?? "longtext";
  const [value, setValue] = useState("");
  const box = useRef<HTMLTextAreaElement>(null);
  const today = iso(new Date());

  useEffect(() => { setValue(""); }, [question?.field]);
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [value]);

  const out = type === "money" || type === "number" ? value.replace(/\s/g, "") : value.trim();
  // the text stays in the box until the server has it (bad connection: nothing is lost)
  const shown = type === "date" && out ? out.split("-").reverse().join(".")
    : type === "money" && out ? `${groupDigits(out)} ${currency === "KZT" ? "₸" : currency ?? ""}`.trim() : undefined;
  const send = async () => { if (out && !busy && (await onSend(out, shown)) !== false) setValue(""); };
  // several documents at once; the camera takes one photo at a time
  const fileInput = (capture: boolean) => (
    <input type="file" className="sr-only" disabled={busy} accept={capture ? "image/*" : DOC_ACCEPT} multiple={!capture}
      {...(capture ? { capture: "environment" as const } : {})}
      onChange={(e) => { const fs = Array.from(e.target.files ?? []); e.target.value = ""; if (fs.length) onFiles(fs); }} />
  );

  if (type === "evidence") {
    const uploaded = (question?.uploaded ?? 0) > 0;
    return (
      <div className="space-y-2">
        <div className="grid grid-cols-2 gap-2">
          <label className={`flex min-h-14 cursor-pointer items-center justify-center gap-2 rounded-2xl bg-brand px-3 font-semibold text-white ${busy ? "pointer-events-none opacity-50" : ""}`}>
            <Icon name="camera" size={20} />{t("app.photo")}{fileInput(true)}
          </label>
          <label className={`flex min-h-14 cursor-pointer items-center justify-center gap-2 rounded-2xl border border-line bg-surface px-3 font-semibold ${busy ? "pointer-events-none opacity-50" : ""}`}>
            <Icon name="upload" size={20} />{t("app.file")}{fileInput(false)}
          </label>
        </div>
        {(uploaded || question?.optional) && (
          <button type="button" disabled={busy} onClick={uploaded ? onDone : onSkip}
            className="min-h-12 w-full rounded-2xl border border-line bg-surface font-semibold hover:border-brand disabled:opacity-50">
            {uploaded ? t("case.doneUploading") : t("case.skip")}
          </button>
        )}
      </div>
    );
  }

  const common = "min-h-12 w-full min-w-0 rounded-2xl border border-line bg-sand px-4 text-base outline-none focus:border-brand focus:bg-surface";
  let field;
  if (type === "date") {
    const y = new Date(); y.setDate(y.getDate() - 1);
    field = (
      <div className="flex min-w-0 flex-1 flex-col gap-2">
        <div className="flex gap-2">
          {[[t("app.today"), today], [t("app.yesterday"), iso(y)]].map(([label, v]) => (
            <button key={v} type="button" disabled={busy} onClick={() => setValue(v)}
              className={`min-h-10 rounded-full border px-4 text-sm font-medium ${value === v ? "border-brand bg-brand-50 text-brand" : "border-line bg-surface"}`}>{label}</button>
          ))}
        </div>
        <label className="relative block">
          <span className="sr-only">{question?.text}</span>
          <Icon name="calendar" size={20} className="pointer-events-none absolute start-4 top-1/2 -translate-y-1/2 text-brand" />
          <input type="date" max={today} value={value} onChange={(e) => setValue(e.target.value)}
            className={`${common} ps-12`} aria-describedby="answer-hint" />
        </label>
      </div>
    );
  } else if (type === "money" || type === "number") {
    field = (
      <label className="relative block min-w-0 flex-1">
        <span className="sr-only">{question?.text}</span>
        {/* The digits stay as typed (reformatting while typing moved the caret and lost digits on phones);
            the grouped amount is shown under the box so a missing or extra zero is easy to see. */}
        <input inputMode={type === "money" ? "numeric" : "decimal"} autoComplete="off" enterKeyHint="send"
          value={value}
          onChange={(e) => setValue(type === "money" ? e.target.value.replace(/\D/g, "").replace(/^0+(?=\d)/, "") : e.target.value.replace(/[^\d.,]/g, ""))}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); send(); } }}
          placeholder={type === "money" ? "0" : ""} className={`${common} pe-14 text-lg tabular-nums`} />
        {type === "money" && <span className="pointer-events-none absolute end-4 top-1/2 -translate-y-1/2 font-semibold text-muted">{currency === "KZT" ? "₸" : currency}</span>}
        {type === "money" && Number(value) > 0 && (
          <span className="mt-1 block px-1 text-sm font-semibold tabular-nums text-ink">{groupDigits(value)} {currency === "KZT" ? "₸" : currency}</span>
        )}
      </label>
    );
  } else if (type === "text" && digitsOnly(question?.pattern)) {
    const len = digitsOnly(question?.pattern)!;
    field = (
      <label className="block min-w-0 flex-1">
        <span className="sr-only">{question?.text}</span>
        <input inputMode="numeric" autoComplete="off" enterKeyHint="send" maxLength={len ?? undefined}
          value={value} onChange={(e) => setValue(e.target.value.replace(/\D/g, ""))}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); send(); } }}
          placeholder={"0".repeat(len || 0) || undefined} className={`${common} text-lg tracking-widest tabular-nums`} />
        {len > 0 && <span className="mt-1 block px-1 text-xs text-muted">{t("app.digits", { n: value.length, total: len })}</span>}
      </label>
    );
  } else if (type === "phone" || type === "email" || type === "text") {
    field = (
      <label className="block min-w-0 flex-1">
        <span className="sr-only">{question?.text}</span>
        <input type={type === "phone" ? "tel" : type === "email" ? "email" : "text"}
          inputMode={type === "phone" ? "tel" : type === "email" ? "email" : "text"}
          autoComplete={type === "phone" ? "tel" : type === "email" ? "email" : "off"} enterKeyHint="send"
          value={value} onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); send(); } }}
          placeholder={type === "phone" ? "+7 700 000 00 00" : type === "email" ? "name@mail.kz" : t("case.answerPlaceholder")}
          className={common} />
      </label>
    );
  } else {
    field = (
      <label className="block min-w-0 flex-1">
        <span className="sr-only">{question?.text ?? placeholder}</span>
        <textarea ref={box} rows={1} value={value} onChange={(e) => setValue(e.target.value)} enterKeyHint="enter"
          placeholder={placeholder ?? t("case.answerPlaceholder")}
          className={`${common} block max-h-40 resize-none py-3 leading-snug`} />
      </label>
    );
  }

  return (
    <form onSubmit={(e) => { e.preventDefault(); send(); }} className="space-y-2">
      {question && type !== "longtext" && (
        <p id="answer-hint" className="px-1 text-xs text-muted">
          {type === "text" && digitsOnly(question.pattern) ? t("app.hint.digits", { n: digitsOnly(question.pattern)! }) : t(`app.hint.${type}`)}
        </p>
      )}
      <div className="flex items-end gap-2">
        <label title={t("chat.attach")}
          className={`flex h-12 w-12 shrink-0 cursor-pointer items-center justify-center rounded-full text-muted hover:bg-sand hover:text-ink ${busy ? "pointer-events-none opacity-50" : ""}`}>
          <Icon name="paperclip" size={22} /><span className="sr-only">{t("chat.attach")}</span>{fileInput(false)}
        </label>
        <label title={t("app.photo")}
          className={`hidden h-12 w-12 shrink-0 cursor-pointer items-center justify-center rounded-full text-muted hover:bg-sand hover:text-ink pointer-coarse:flex ${busy ? "pointer-events-none opacity-50" : ""}`}>
          <Icon name="camera" size={22} /><span className="sr-only">{t("app.photo")}</span>{fileInput(true)}
        </label>
        {field}
        <button type="submit" disabled={busy || !out} aria-label={t("case.send")}
          className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-brand text-white disabled:opacity-40">
          <Icon name={busy ? "spinner" : "send"} size={20} />
        </button>
      </div>
      {question?.optional && (
        <button type="button" disabled={busy} onClick={onSkip} className="px-1 text-sm font-medium text-brand disabled:opacity-50">
          {t("case.skip")}
        </button>
      )}
    </form>
  );
}
