"use client";

import { usePathname } from "next/navigation";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Icon, type IconName } from "@/components/ui";
import { useT } from "@/lib/i18n";
import { enablePush, isIos, isStandalone, pushState } from "@/lib/push";

type PromptEvent = Event & { prompt: () => Promise<void>; userChoice: Promise<{ outcome: string }> };
declare global {
  // kept by the inline INSTALL_CAPTURE script of app/layout.tsx, which listens before any of the app's code has loaded
  interface Window { __konsilierInstall?: PromptEvent | null }
}

/**
 * How this device installs the app:
 * - "prompt": the browser's own install dialog (Chrome / Edge / Samsung Internet on Android, Windows, Mac);
 * - "ios": Safari on iPhone / iPad (Apple offers no install API: Share → «На экран „Домой“»);
 * - "iosBrowser": Chrome, Edge, Firefox on iPhone / iPad — since iOS 16.4 they add to the home screen from Share too;
 * - "iosInApp": a browser inside another app (Telegram, Instagram, WhatsApp, Google app…) or a non-Safari browser before
 *   iOS 16.4: only a real browser installs, so the tap opens the page in Safari (x-safari-https:, iOS 17+) or Chrome;
 * - "androidInApp": the same on Android: the tap opens the page in Chrome (intent: link);
 * - "macSafari": Safari 17+ on Mac (File → Add to Dock);
 * - "menu": a browser that installs from its menu but has not offered a dialog (yet): any Android browser; Chrome, Edge,
 *   Yandex, Opera, Brave on a computer — hintFor() gives the steps for that very browser;
 * - "other": a browser that cannot install (Firefox on a computer); "installed": already done.
 */
export type Platform = "installed" | "otherApp" | "prompt" | "ios" | "iosBrowser" | "iosInApp" | "androidInApp" | "macSafari" | "menu" | "other";

const INSTALLED = "konsilier.installed"; // Chromium installed the app from this browser (it offers no dialog since)
const CHANGED = "konsilier:install";     // the install state changed: every button and banner re-reads it
const DONE = "konsilier:installed";      // the browser's dialog installed the app just now
// browsers inside other apps: they cannot install, a real browser can
const IN_APP = /FBAN|FBAV|Instagram|Line\/|Telegram|TikTok|musical_ly|Snapchat|VKClient|WhatsApp|GSA\//;

function read(key: string): string | null {
  try { return localStorage.getItem(key); } catch { return null; }
}
function write(key: string, value: string | null) {
  try { if (value === null) localStorage.removeItem(key); else localStorage.setItem(key, value); } catch {}
}

/** Registers the service worker (production only) so the site can be installed as an app. */
export function PwaRegister() {
  useEffect(() => {
    if (process.env.NODE_ENV !== "production" || !("serviceWorker" in navigator)) return;
    navigator.serviceWorker.register("/sw.js", { scope: "/", updateViaCache: "none" }).then((reg) => {
      // a tab or an installed app left open for days: check for a new service worker when it comes back
      const again = () => { if (document.visibilityState === "visible") reg.update().catch(() => {}); };
      document.addEventListener("visibilitychange", again);
    }).catch(() => {});
  }, []);
  return null;
}

const WINDOW = "konsilier.window"; // which installed app this window is: "ops" or "client" (set at its start URL)

/** The installed app this window was started as, from its start URL (/ops?source=app or /?source=app); kept per window. */
function appWindow(): string | null {
  try {
    const { pathname, search } = window.location;
    if (new URLSearchParams(search).get("source") === "app") sessionStorage.setItem(WINDOW, pathname.startsWith("/ops") ? "ops" : "client");
    return sessionStorage.getItem(WINDOW);
  } catch { return null; }
}

export function detect(storeKey: string = INSTALLED): Platform {
  const app = appWindow();
  if (storeKey !== INSTALLED) {
    // «Konsiliér Ops» (/ops, its own manifest): trust only a positive signal of which window this is — a browser tab
    // must never hide the button (owner 01.10: the hint showed in an ordinary Chrome tab)
    if (app === "ops") return "installed";
    if (app === "client" && isStandalone()) return "otherApp";
  } else if (isStandalone() && !matchMedia("(display-mode: browser)").matches) {
    return "installed"; // running as the app
  }
  if (window.__konsilierInstall) return "prompt";
  if (read(storeKey) === "1") return "installed";
  const ua = navigator.userAgent;
  if (isIos()) {
    if (IN_APP.test(ua) || !/Safari\//.test(ua)) return "iosInApp"; // an app's own web view has no «Safari/» in its name
    if (!/CriOS|FxiOS|EdgiOS|OPiOS|OPT\/|YaBrowser/.test(ua)) return "ios";
    // other browsers add to the home screen from Share since iOS 16.4; before that only Safari can
    const [, major, minor] = /OS (\d+)_(\d+)/.exec(ua) ?? [];
    return major && (Number(major) < 16 || (Number(major) === 16 && Number(minor) < 4)) ? "iosInApp" : "iosBrowser";
  }
  if (/Macintosh/.test(ua) && /Version\/(1[7-9]|[2-9]\d)/.test(ua) && /Safari\//.test(ua) && !/Chrome|Chromium|Edg|OPR|Firefox/.test(ua)) {
    return "macSafari";
  }
  if (/Android/.test(ua) && (IN_APP.test(ua) || /; wv\)/.test(ua))) return "androidInApp";
  if (/Android/.test(ua)) return "menu"; // Chrome, Edge, Samsung, Firefox, Opera, Yandex on Android all install from their menu
  // Chrome, Edge, Yandex, Opera, Brave on a computer; Firefox there cannot install (Hint says so honestly)
  if (/Chrome|Chromium|Edg|OPR|YaBrowser/.test(ua) && !/Firefox/.test(ua)) return "menu";
  return "other";
}

type Pointer = "top" | "bottom" | "bottomEnd" | null;

/** The steps for this very browser — never «use another browser» where this one installs — and where its button is. */
export function hintFor(platform: Platform, ua: string, ipad: boolean): { key: string; pointer: Pointer } {
  const phone = !ipad;
  if (platform === "ios") {
    // Safari 26 on iPhone keeps Share in the «•••» menu at the bottom right; before, Share sat mid-bottom; iPad: top right
    const safari26 = Number(/Version\/(\d+)/.exec(ua)?.[1] ?? 0) >= 26;
    return safari26 && phone ? { key: "ios26", pointer: "bottomEnd" } : { key: "ios", pointer: ipad ? "top" : "bottom" };
  }
  if (platform === "iosBrowser") {
    if (/CriOS/.test(ua)) return { key: "iosChrome", pointer: "top" };   // Share at the right of the address bar
    if (/EdgiOS/.test(ua)) return { key: "iosEdge", pointer: ipad ? "top" : "bottom" };
    if (/FxiOS/.test(ua)) return { key: "iosFirefox", pointer: ipad ? "top" : "bottomEnd" };
    return { key: "iosOther", pointer: null };
  }
  if (platform === "menu") {
    if (/Android/.test(ua)) {
      if (/SamsungBrowser/.test(ua)) return { key: "androidSamsung", pointer: "bottomEnd" };
      if (/Firefox/.test(ua)) return { key: "androidFirefox", pointer: null };
      if (/EdgA\//.test(ua)) return { key: "androidEdge", pointer: "bottom" };
      if (/OPR|YaBrowser/.test(ua)) return { key: "menu", pointer: null };
      return { key: "androidChrome", pointer: "top" };
    }
    if (/Edg\//.test(ua)) return { key: "desktopEdge", pointer: "top" };
    if (/OPR|YaBrowser/.test(ua)) return { key: "desktopOther", pointer: "top" };
    return { key: "desktopChrome", pointer: "top" };
  }
  if (platform === "other" && /Firefox/.test(ua)) return { key: "firefox", pointer: null };
  return { key: platform, pointer: null };
}

/** Chrome can offer its dialog a moment after the page opens: wait for it up to 3 s before giving up. */
function lateDialog(): Promise<PromptEvent | null> {
  return new Promise((resolve) => {
    const done = () => { window.removeEventListener("beforeinstallprompt", done); clearTimeout(timer); resolve(window.__konsilierInstall ?? null); };
    const timer = setTimeout(done, 3000);
    window.addEventListener("beforeinstallprompt", done);
  });
}

/** Opens this page (/app, or /ops for Konsiliér Ops) in the device's real browser, from a browser inside another app. */
function realBrowserLink(platform: Platform, browser: "safari" | "chrome" = "safari"): string {
  const { host, pathname } = window.location;
  const page = `${host}${pathname.startsWith("/ops") ? "/ops" : "/app"}?install=1`;
  if (platform === "androidInApp") {
    const back = encodeURIComponent(`https://${page}`);
    return `intent://${page}#Intent;scheme=https;package=com.android.chrome;S.browser_fallback_url=${back};end`;
  }
  return browser === "chrome" ? `googlechromes://${page}` : `x-safari-https://${page}`;
}

/** The platform (null until known on the client) and the install action: the browser's own dialog, straight away.
 * `storeKey`: where this browser remembers that the app is installed — the command centre (/ops, its own manifest)
 * is a second app and keeps its own flag. */
export function useInstall(storeKey: string = INSTALLED) {
  const [platform, setPlatform] = useState<Platform | null>(null);
  useEffect(() => {
    const update = () => setPlatform(detect(storeKey));
    const onPrompt = () => { write(storeKey, null); update(); }; // offered again: the app is not installed
    const onInstalled = () => { write(storeKey, "1"); update(); };
    update();
    // Chrome gives no install dialog once the app is installed; it can say so (manifest related_applications)
    const nav = navigator as Navigator & { getInstalledRelatedApps?: () => Promise<{ platform: string }[]> };
    nav.getInstalledRelatedApps?.().then((apps) => {
      if (apps.some((a) => a.platform === "webapp") && !window.__konsilierInstall) { write(storeKey, "1"); update(); }
    }).catch(() => {});
    // the layout's INSTALL_CAPTURE was registered first, so window.__konsilierInstall is set by the time these run
    window.addEventListener("beforeinstallprompt", onPrompt);
    window.addEventListener("appinstalled", onInstalled);
    window.addEventListener(CHANGED, update);
    return () => {
      window.removeEventListener("beforeinstallprompt", onPrompt);
      window.removeEventListener("appinstalled", onInstalled);
      window.removeEventListener(CHANGED, update);
    };
  }, [storeKey]);
  const install = useCallback(async (): Promise<boolean> => {
    const e = window.__konsilierInstall ?? await lateDialog();
    if (!e) return false;
    window.__konsilierInstall = null; // the dialog opens once per event
    let accepted = false;
    try {
      await e.prompt();
      accepted = (await e.userChoice).outcome === "accepted";
    } catch {}
    if (accepted) write(storeKey, "1");
    window.dispatchEvent(new Event(CHANGED));
    return accepted;
  }, [storeKey]);
  return { platform, install };
}

/** The one line for a device without an install dialog; {share} becomes the Share icon. */
function Hint({ platform, text, onClose }: { platform: Platform; text?: string; onClose: () => void }) {
  const t = useT();
  const close = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    close.current?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const ua = navigator.userAgent;
  const ipad = /iPad/.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1);
  const { key, pointer: browserPointer } = hintFor(platform, ua, ipad);
  const inApp = platform === "iosInApp" || platform === "androidInApp";
  const [before, after] = (text ?? t(`pwa.hint.${key}`, { site: window.location.host })).split("{share}");
  const line: ReactNode = after === undefined ? before : (
    <>{before}<Icon name="share" size={22} className="mx-1 inline-block -translate-y-0.5 text-action" />{after}</>
  );
  const pointer = text ? null : browserPointer;

  return createPortal(
    <div className="fixed inset-0 z-50" onClick={onClose}>
      <div className="absolute inset-0 bg-black/30" aria-hidden="true" />
      <div role="dialog" aria-modal="true" aria-label={t("pwa.install")} onClick={(e) => e.stopPropagation()}
        className={`absolute inset-x-3 mx-auto flex max-w-md items-center gap-3 rounded-2xl bg-surface py-4 ps-5 pe-2 shadow-[0_12px_40px_rgb(0_0_0/0.2)] ${
          pointer === "top" ? "top-[calc(3.5rem+env(safe-area-inset-top))]" : "bottom-[calc(3.5rem+env(safe-area-inset-bottom))]"}`}>
        <div className="flex-1 space-y-3">
          <p className="text-[17px] leading-snug font-medium whitespace-pre-line">{line}</p>
          {inApp && !text && (
            // one tap: the page opens in Safari / Chrome, where «Установить» works
            <a href={realBrowserLink(platform)} className="btn-primary min-h-11 w-full justify-center">
              {t(platform === "androidInApp" ? "pwa.openChrome" : "pwa.openSafari")}
            </a>
          )}
          {platform === "iosInApp" && !text && (
            // Chrome on iPhone installs too: for those who keep it as their browser
            <a href={realBrowserLink(platform, "chrome")} className="btn-ghost min-h-11 w-full justify-center">{t("pwa.openChrome")}</a>
          )}
          {platform === "ios" && !text && (
            // inside a Telegram / Instagram viewer iOS has no «На экран „Домой“»: open the page in Safari itself
            <a href={realBrowserLink("iosInApp")} className="block text-sm text-muted underline">{t("pwa.noHomeScreen")}</a>
          )}
        </div>
        <button ref={close} type="button" onClick={onClose} aria-label={t("app.close")}
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-muted hover:bg-sand"><Icon name="x" size={20} /></button>
      </div>
      {pointer && (
        // points at Safari's own button, outside the page: bottom middle (iPhone), bottom right (iPhone, Safari 26), top right (iPad)
        <span aria-hidden="true"
          className={`absolute flex h-10 w-10 items-center justify-center rounded-full bg-action text-white shadow-lg motion-safe:animate-bounce ${
            pointer === "top" ? "top-[calc(0.5rem+env(safe-area-inset-top))] right-5"
              : `bottom-[calc(0.5rem+env(safe-area-inset-bottom))] ${pointer === "bottom" ? "left-1/2 -ml-5" : "right-4"}`}`}>
          <Icon name="arrowUp" size={22} className={pointer === "top" ? "" : "rotate-180"} />
        </span>
      )}
    </div>,
    document.body,
  );
}

/**
 * «Установить». Where the browser can install (Android, Windows, Chrome / Edge on Mac), the tap opens its own dialog —
 * nothing else. Elsewhere the tap shows one line in a small sheet (iPhone: Share → «На экран „Домой“»).
 * Hidden when the app is installed.
 */
export function InstallButton({ className, icon, onInstalled, storeKey, label }:
  { className: string; icon?: IconName; onInstalled?: () => void; storeKey?: string; label?: string }) {
  const t = useT();
  const { platform, install } = useInstall(storeKey);
  const [hint, setHint] = useState<Platform | null>(null);
  const [waiting, setWaiting] = useState(false);
  const closeHint = useCallback(() => setHint(null), []);
  // inside another installed app's window the browser offers no install: open the page in the browser first
  const otherAppText = "Сейчас открыто окно приложения Konsiliér AI. Нажмите ⋮ справа вверху → «Открыть в Chrome» (Open in Chrome) и там — «Установить на рабочий стол».";
  // /app?install=1 — the page was just opened in Safari / Chrome from another app's browser: continue at once
  useEffect(() => {
    if (platform !== "ios" && platform !== "iosBrowser") return;
    if (new URLSearchParams(window.location.search).get("install") === "1") setHint(platform);
  }, [platform]);

  if (platform === null || platform === "installed") return null;
  const go = async () => {
    if (platform === "menu") {
      // Chrome / Edge that has not offered its dialog yet: wait for it briefly rather than show steps at once
      setWaiting(true);
      const ok = await install();
      setWaiting(false);
      if (ok) { window.dispatchEvent(new Event(DONE)); onInstalled?.(); return; }
      if (detect(storeKey) === "installed") return;
      setHint(platform);
      return;
    }
    if (platform === "prompt") {
      if (await install()) {
        window.dispatchEvent(new Event(DONE)); // the note on where the icon is lives in AppBanner, which stays mounted
        onInstalled?.();
      }
      return;
    }
    setHint(platform);
  };
  return (
    <>
      <button type="button" onClick={go} disabled={waiting} aria-busy={waiting} className={className}>
        {icon && <Icon name={icon} size={18} />}{label ?? t("pwa.install")}
      </button>
      {hint && <Hint platform={hint} onClose={closeHint} text={hint === "otherApp" ? otherAppText : undefined} />}
    </>
  );
}

/** The install button of the header menu and the footer. */
export function InstallApp({ className = "" }: { className?: string }) {
  return (
    <div className={className} onClickCapture={(e) => e.currentTarget.closest("details")?.removeAttribute("open")}>
      <InstallButton icon="smartphone"
        className="inline-flex min-h-11 items-center gap-2 rounded-xl border border-line bg-surface px-3 text-sm font-semibold hover:border-brand hover:text-brand [&>svg]:text-brand" />
    </div>
  );
}

const VISITS = "konsilier.visits";
const BANNER = "konsilier.appBanner";   // "dismissed": the install banner is not shown again
const PUSH_BANNER = "konsilier.pushBanner";
// full-screen screens (a case, a chat) and the pages that already are about the app get no banner
const QUIET = ["/case/", "/chat/", "/app", "/share", "/account"];

/**
 * A small banner on phones. In the browser, for a returning visitor (second visit on): «Установить» — the same
 * one-tap install as everywhere. In the installed app: «Включить уведомления» once, until done or dismissed.
 * Dismissal is remembered.
 */
export function AppBanner({ above = false }: { above?: boolean }) {
  const [done, setDone] = useState(false);
  useEffect(() => {
    const onDone = () => setDone(true);
    window.addEventListener(DONE, onDone);
    return () => window.removeEventListener(DONE, onDone);
  }, []);
  const t = useT();
  const path = usePathname();
  const { platform } = useInstall();
  const [kind, setKind] = useState<"install" | "push" | null>(null);

  useEffect(() => {
    try {  // a visit = a browser session
      if (!sessionStorage.getItem(VISITS)) {
        sessionStorage.setItem(VISITS, "1");
        write(VISITS, String(Number(read(VISITS) ?? "0") + 1));
      }
    } catch {}
    const phone = matchMedia("(pointer: coarse)").matches && matchMedia("(max-width: 1023px)").matches;
    if (!phone) return;
    if (isStandalone()) {
      if (read(PUSH_BANNER) !== "dismissed") pushState().then((s) => { if (s === "ready") setKind("push"); }).catch(() => {});
    } else if (read(BANNER) !== "dismissed" && Number(read(VISITS) ?? "0") >= 2) {
      setKind("install");
    }
  }, []);

  if (done) {
    // where the icon is now: the browser puts it there, the site cannot choose
    const ua = navigator.userAgent;
    const where = /Android/.test(ua) ? "android" : /Windows/.test(ua) ? "windows" : /Macintosh/.test(ua) ? "mac" : "other";
    return <Hint platform="installed" text={t(`pwa.done.${where}`)} onClose={() => setDone(false)} />;
  }
  if (!kind || QUIET.some((q) => path === q || path.startsWith(q))) return null;
  if (kind === "install" && (platform === null || platform === "installed")) return null;
  const dismiss = () => { write(kind === "push" ? PUSH_BANNER : BANNER, "dismissed"); setKind(null); };
  const enable = async () => {
    await enablePush().catch(() => null);
    dismiss();
  };
  return (
    <div role="region" aria-label={t(kind === "push" ? "push.title" : "pwa.bannerTitle")}
      className={`fixed inset-x-3 z-30 lg:hidden ${above ? "bottom-[calc(4.75rem+env(safe-area-inset-bottom))]" : "bottom-[calc(0.75rem+env(safe-area-inset-bottom))]"}`}>
      <div className="mx-auto flex max-w-lg items-center gap-3 rounded-2xl bg-surface p-3 shadow-[0_8px_30px_rgb(0_0_0/0.16)] ring-1 ring-ink/[0.06]">
        <Icon name={kind === "push" ? "bell" : "smartphone"} size={22} className="shrink-0 text-brand" />
        <p className="min-w-0 flex-1 text-sm leading-snug">
          <span className="block font-semibold">{t(kind === "push" ? "push.short" : "pwa.bannerTitle")}</span>
          {kind === "install" && <span className="block text-muted">{t("pwa.bannerText")}</span>}
        </p>
        {kind === "install"
          ? <InstallButton onInstalled={dismiss} className="btn-primary min-h-9 shrink-0 px-3 text-sm" />
          : <button type="button" onClick={enable} className="btn-primary min-h-9 shrink-0 px-3 text-sm">{t("push.enable")}</button>}
        <button type="button" onClick={dismiss} aria-label={t("app.close")}
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-muted hover:bg-sand"><Icon name="x" size={18} /></button>
      </div>
    </div>
  );
}
