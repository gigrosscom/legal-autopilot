"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, NetworkError, transcribeAudio } from "./api";

// Voice input, on every device. Where the browser has speech recognition that works (Chrome, Edge, Safari) it is
// used: no server, no cost, live interim text. Elsewhere (Firefox, iOS home-screen apps, some Android WebViews)
// the voice is recorded with MediaRecorder and sent to POST /v1/transcribe (free Gemini, audio not stored).
// Speech synthesis (reading replies aloud) is the device's own.
const LOCALES: Record<string, string> = { ru: "ru-RU", kk: "kk-KZ", en: "en-US", tr: "tr-TR", ar: "ar-SA" };
export const MAX_RECORDING_MS = 120_000; // the server accepts about two minutes
const LIVE_EVERY_MS = 1500; // the recording fallback: live text this often while speaking
const LIVE_FIRST_MS = 600; // …and the first time this soon after the recording starts
const MAX_SPEECH_MS = 600_000; // built-in recognition is restarted after pauses for up to ten minutes

/** Two pieces of dictated text with one space between them. */
export function joinText(a: string, b: string): string {
  const x = a.trim(), y = b.trim();
  return x && y ? `${x} ${y}` : x || y;
}

type Recognition = {
  lang: string; continuous: boolean; interimResults: boolean;
  onresult: ((e: { resultIndex: number; results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }> }) => void) | null;
  onend: (() => void) | null; onerror: ((e: { error: string }) => void) | null;
  start: () => void; stop: () => void;
};

/** iOS home-screen app: webkitSpeechRecognition is defined there but does not work. */
function iosStandalone(): boolean {
  if (typeof window === "undefined") return false;
  const nav = navigator as Navigator & { standalone?: boolean };
  const ios = /iPad|iPhone|iPod/.test(nav.userAgent) || (nav.platform === "MacIntel" && nav.maxTouchPoints > 1);
  return ios && (nav.standalone === true || window.matchMedia?.("(display-mode: standalone)").matches === true);
}

function recognitionCtor(): (new () => Recognition) | null {
  if (typeof window === "undefined" || iosStandalone()) return null;
  const w = window as unknown as { SpeechRecognition?: new () => Recognition; webkitSpeechRecognition?: new () => Recognition };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

function canRecord(): boolean {
  return typeof window !== "undefined" && typeof window.MediaRecorder !== "undefined"
    && !!navigator.mediaDevices && typeof navigator.mediaDevices.getUserMedia === "function";
}

/** A container the recorder supports: Opus in WebM (Chrome, Firefox, Android), MP4/AAC (Safari). */
function recorderType(): string {
  const types = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus", "audio/aac"];
  return types.find((t) => { try { return MediaRecorder.isTypeSupported(t); } catch { return false; } }) ?? "";
}

function extension(mime: string): string {
  const m = mime.split(";")[0];
  return m.endsWith("mp4") ? "m4a" : m.endsWith("ogg") ? "ogg" : m.endsWith("aac") ? "aac" : m.endsWith("wav") ? "wav" : "webm";
}

/** Web Speech error → the code shown as t(`chat.errors.${code}`); null: nothing to show. */
function speechErrorCode(e: string): string | null {
  if (e === "not-allowed") return "mic_denied";
  if (e === "audio-capture") return "no_mic";
  if (e === "no-speech") return "no_speech";
  if (e === "aborted") return null;
  return "mic_failed";
}

function uploadErrorCode(e: unknown): string {
  if (e instanceof ApiError) return e.code ?? (e.status === 429 ? "too_many_transcriptions" : "transcribe_failed");
  if (e instanceof NetworkError) return "transcribe_network";
  return "transcribe_failed";
}

/**
 * Voice input on every device. While listening, `onText(text)` receives everything said since `start()`, interim
 * words included, each time it changes (so the box can show it live); with the recording fallback the text so far
 * arrives every ~1.5 s while speaking and the final text after `stop()` (or the 2-minute limit) and the upload
 * (`transcribing` is true meanwhile). `error` is a code for t(`chat.errors.${error}`): mic_denied, no_mic,
 * no_speech, mic_failed, transcribe_unavailable, transcribe_busy, transcribe_failed, transcribe_network,
 * too_many_transcriptions, audio_too_large.
 */
export function useVoiceInput(lang: string, onText: (text: string) => void) {
  const [supported, setSupported] = useState(false);
  const [listening, setListening] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const rec = useRef<Recognition | null>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [startedAt, setStartedAt] = useState(0);  // Date.now() when the dictation began, for the timer
  const stopped = useRef(true);  // the person pressed stop (or an error ended it): no automatic restart
  const speechBroken = useRef(false); // Web Speech exists but its service fails here (WebViews, Brave…)
  const alive = useRef(true);
  const cb = useRef(onText);
  cb.current = onText;
  const langRef = useRef(lang);
  langRef.current = lang;

  useEffect(() => {
    alive.current = true;
    setSupported(recognitionCtor() !== null || canRecord());
    return () => { alive.current = false; };
  }, []);

  const startRecording = useCallback(async () => {
    if (!canRecord()) { setError("mic_failed"); return; }
    setError(null);
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
    } catch (e) {
      const name = (e as { name?: string })?.name;
      setError(name === "NotAllowedError" || name === "SecurityError" ? "mic_denied"
        : name === "NotFoundError" || name === "OverconstrainedError" ? "no_mic" : "mic_failed");
      return;
    }
    if (!alive.current) { stream.getTracks().forEach((t) => t.stop()); return; }
    const type = recorderType();
    let r: MediaRecorder;
    try {
      r = type ? new MediaRecorder(stream, { mimeType: type }) : new MediaRecorder(stream);
    } catch {
      stream.getTracks().forEach((t) => t.stop());
      setError("mic_failed");
      return;
    }
    const chunks: Blob[] = [];
    r.ondataavailable = (e) => { if (e.data && e.data.size > 0) chunks.push(e.data); };
    // Live text (owner 01.10, iPhone app): while recording, the audio so far is sent every ~1.5 s and what the server
    // hears so far is shown in the box; one request at a time, the final text after «Стоп» replaces it. A busy or
    // limited server just pauses the live text — the final transcription is unaffected.
    const mimeOf = () => r.mimeType || type || "audio/webm";
    let inFlight = false, sentChunks = 0, pauseUntil = 0, finished = false, lastSent = 0;
    const began = Date.now();
    const live = setInterval(async () => {
      const now = Date.now();
      // the first words as soon as there is a little audio (the person sees it work), then every LIVE_EVERY_MS
      const due = sentChunks === 0 ? now - began >= LIVE_FIRST_MS : now - lastSent >= LIVE_EVERY_MS;
      if (finished || inFlight || !due || chunks.length === sentChunks || now < pauseUntil) return;
      inFlight = true;
      sentChunks = chunks.length;
      lastSent = now;
      const mime = mimeOf();
      try {
        const text = (await transcribeAudio(new Blob(chunks, { type: mime.split(";")[0] }), langRef.current,
          `voice.${extension(mime)}`, true)).trim();
        if (!finished && alive.current && text) cb.current(text);
      } catch {
        pauseUntil = Date.now() + 10_000;  // busy or over the limit: try again a little later
      } finally { inFlight = false; }
    }, 200);
    r.onstop = async () => {
      finished = true;
      clearInterval(live);
      stream.getTracks().forEach((t) => t.stop());
      if (timer.current) { clearTimeout(timer.current); timer.current = null; }
      recorder.current = null;
      if (!alive.current) return;
      setListening(false);
      const mime = r.mimeType || type || "audio/webm";
      const blob = new Blob(chunks, { type: mime.split(";")[0] });
      if (blob.size === 0) { setError("no_speech"); return; }
      setTranscribing(true);
      try {
        const text = (await transcribeAudio(blob, langRef.current, `voice.${extension(mime)}`)).trim();
        if (!alive.current) return;
        if (text) cb.current(text); else setError("no_speech");
      } catch (e) {
        if (alive.current) setError(uploadErrorCode(e));
      } finally {
        if (alive.current) setTranscribing(false);
      }
    };
    recorder.current = r;
    r.start(500); // a chunk every half second: the live text has audio early, nothing is lost on an abrupt stop
    setListening(true);
    timer.current = setTimeout(() => { if (r.state !== "inactive") r.stop(); }, MAX_RECORDING_MS);
  }, []);

  const stop = useCallback(() => {
    stopped.current = true;
    if (recorder.current && recorder.current.state !== "inactive") recorder.current.stop();
    rec.current?.stop();
  }, []);

  const start = useCallback(() => {
    if (listening || transcribing) return;
    const Ctor = speechBroken.current ? null : recognitionCtor();
    setStartedAt(Date.now());
    if (!Ctor) { void startRecording(); return; }
    stopped.current = false;
    let committed = "";  // text of earlier recognisers in this dictation (the browser ends one after a pause)
    let heardAny = false;
    const began = Date.now();
    const launch = (): boolean => {
      const r = new Ctor();
      r.lang = LOCALES[langRef.current] ?? langRef.current;
      r.continuous = true;
      r.interimResults = true;
      let heard = false;
      let current = "";
      r.onresult = (e) => {
        heard = true; heardAny = true;
        // rebuilt from every result each time: Safari on iOS re-sends and revises earlier results
        let fin = "", interim = "";
        for (let i = 0; i < e.results.length; i++) {
          const res = e.results[i];
          if (res.isFinal) fin += res[0].transcript; else interim += res[0].transcript;
        }
        current = joinText(fin, interim);
        cb.current(joinText(committed, current));
      };
      r.onerror = (e) => {
        // the speech service is missing or blocked here: record and transcribe on the server instead
        if (!heardAny && canRecord()
            && (e.error === "network" || e.error === "service-not-allowed" || e.error === "language-not-supported")) {
          speechBroken.current = true;
          r.onend = null;
          rec.current = null;
          setListening(false);
          void startRecording();
          return;
        }
        if (e.error === "no-speech" && heardAny) return;  // a pause after some words: not an error
        if (e.error !== "no-speech" && e.error !== "aborted") stopped.current = true;
        setError(speechErrorCode(e.error));
      };
      r.onend = () => {
        if (rec.current !== r) return;
        committed = joinText(committed, current);
        // the browser ended after a pause while the person had not pressed stop: keep listening
        if (!stopped.current && heard && Date.now() - began < MAX_SPEECH_MS && launch()) return;
        rec.current = null;
        setListening(false);
      };
      rec.current = r;
      try { r.start(); return true; } catch { rec.current = null; return false; }
    };
    setError(null);
    setListening(true);
    if (!launch()) {
      setListening(false);
      speechBroken.current = true;
      void startRecording();
    }
  }, [listening, transcribing, startRecording]);

  useEffect(() => () => {
    stopped.current = true;
    rec.current?.stop();
    if (recorder.current && recorder.current.state !== "inactive") recorder.current.stop();
    if (timer.current) clearTimeout(timer.current);
  }, []);

  return { supported, listening, transcribing, error, startedAt, start, stop };
}

/** Former name, kept for existing callers: the same hook (now with the recording fallback). */
export const useDictation = useVoiceInput;

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
