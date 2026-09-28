"use client";

import { createContext, useContext, useEffect, useState, type ReactNode, useCallback } from "react";

import type { Dict } from "./dict/types";
import ru from "./dict/ru";
import kk from "./dict/kk";
import en from "./dict/en";
import ar from "./dict/ar";
import tr from "./dict/tr";

export type Lang = "ru" | "kk" | "en" | "ar" | "tr";

/** Interface languages. `short` is what the switcher shows; `dir` drives right-to-left layout. */
export const LANGS: { code: Lang; short: string; name: string; dir: "ltr" | "rtl" }[] = [
  { code: "ru", short: "RU", name: "Русский", dir: "ltr" },
  { code: "kk", short: "KK", name: "Қазақша", dir: "ltr" },
  { code: "en", short: "EN", name: "English", dir: "ltr" },
  { code: "ar", short: "AR", name: "العربية", dir: "rtl" },
  { code: "tr", short: "TR", name: "Türkçe", dir: "ltr" },
];

const dicts: Record<Lang, Dict> = { ru, kk, en, ar, tr };
// Missing keys fall back to English, then Russian (the most complete dictionary).
const FALLBACK: Lang[] = ["en", "ru"];

function lookup(dict: Dict, key: string): string | undefined {
  let node: string | Dict | undefined = dict;
  for (const part of key.split(".")) {
    if (typeof node !== "object" || node === null) return undefined;
    node = node[part];
  }
  return typeof node === "string" ? node : undefined;
}

export function isLang(v: unknown): v is Lang {
  return typeof v === "string" && LANGS.some((l) => l.code === v);
}

export function dirOf(lang: Lang): "ltr" | "rtl" {
  return LANGS.find((l) => l.code === lang)?.dir ?? "ltr";
}

const LangContext = createContext<{ lang: Lang; setLang: (l: Lang) => void }>({ lang: "ru", setLang: () => {} });

export function LangProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>("ru");
  useEffect(() => {
    try {
      const saved = localStorage.getItem("konsilier.lang");
      if (isLang(saved)) setLangState(saved);
    } catch {}
  }, []);
  // <html lang dir> follow the chosen language (screen readers, RTL layout, error messages in lib/api).
  useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.dir = dirOf(lang);
  }, [lang]);
  const setLang = (l: Lang) => {
    setLangState(l);
    try {
      localStorage.setItem("konsilier.lang", l);
    } catch {}
  };
  return <LangContext.Provider value={{ lang, setLang }}>{children}</LangContext.Provider>;
}

export function useLang() {
  return useContext(LangContext);
}

export function translate(lang: Lang, key: string, vars?: Record<string, string | number>): string {
  let text = lookup(dicts[lang], key);
  for (const fb of FALLBACK) text ??= lookup(dicts[fb], key);
  text ??= key;
  if (vars) for (const [k, v] of Object.entries(vars)) text = text.replaceAll(`{${k}}`, String(v));
  return text;
}

/** Stable per language, so effects that depend on `t` run again only when the language changes. */
export function useT() {
  const { lang } = useLang();
  return useCallback((key: string, vars?: Record<string, string | number>) => translate(lang, key, vars), [lang]);
}
