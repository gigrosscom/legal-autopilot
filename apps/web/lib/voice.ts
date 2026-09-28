"use client";

import { useCallback, useEffect, useRef, useState } from "react";

// Speech recognition and speech synthesis built into the browser: no server, no cost. Recognition exists in
// Chrome, Edge and Safari (Chrome sends the audio to its own speech service); Firefox has none, so the mic
// button hides there.
const LOCALES: Record<string, string> = { ru: "ru-RU", kk: "kk-KZ", en: "en-US", tr: "tr-TR", ar: "ar-SA" };

type Recognition = {
  lang: string; continuous: boolean; interimResults: boolean;
  onresult: ((e: { resultIndex: number; results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }> }) => void) | null;
  onend: (() => void) | null; onerror: ((e: { error: string }) => void) | null;
  start: () => void; stop: () => void;
};

function recognitionCtor(): (new () => Recognition) | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as { SpeechRecognition?: new () => Recognition; webkitSpeechRecognition?: new () => Recognition };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

/** Dictation: while listening, `onText(final, interim)` receives what was said. */
export function useDictation(lang: string, onText: (finalText: string, interim: string) => void) {
  const [supported, setSupported] = useState(false);
  const [listening, setListening] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const rec = useRef<Recognition | null>(null);
  const cb = useRef(onText);
  cb.current = onText;

  useEffect(() => setSupported(recognitionCtor() !== null), []);

  const stop = useCallback(() => rec.current?.stop(), []);
  const start = useCallback(() => {
    const Ctor = recognitionCtor();
    if (!Ctor) return;
    const r = new Ctor();
    r.lang = LOCALES[lang] ?? lang;
    r.continuous = true;
    r.interimResults = true;
    r.onresult = (e) => {
      let fin = "", interim = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const res = e.results[i];
        if (res.isFinal) fin += res[0].transcript; else interim += res[0].transcript;
      }
      cb.current(fin, interim);
    };
    r.onerror = (e) => setError(e.error);
    r.onend = () => setListening(false);
    rec.current = r;
    setError(null);
    setListening(true);
    r.start();
  }, [lang]);

  useEffect(() => () => rec.current?.stop(), []);
  return { supported, listening, error, start, stop };
}

/** Read a reply aloud with the device's voice for the language. */
export function speak(text: string, lang: string) {
  if (typeof window === "undefined" || !("speechSynthesis" in window)) return false;
  window.speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.lang = LOCALES[lang] ?? lang;
  const voice = window.speechSynthesis.getVoices().find((v) => v.lang.startsWith(u.lang.slice(0, 2)));
  if (voice) u.voice = voice;
  window.speechSynthesis.speak(u);
  return true;
}

export function stopSpeaking() {
  if (typeof window !== "undefined" && "speechSynthesis" in window) window.speechSynthesis.cancel();
}

export const canSpeak = () => typeof window !== "undefined" && "speechSynthesis" in window;
