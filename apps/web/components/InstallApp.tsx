"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { Icon } from "@/components/ui";
import { useT } from "@/lib/i18n";
import { enablePush, isIos, isStandalone, pushState } from "@/lib/push";

type PromptEvent = Event & { prompt: () => Promise<void>; userChoice: Promise<{ outcome: string }> };
/** How this device installs the app: the browser's own dialog, Safari's steps, the browser menu, or already done. */
export type Platform = "installed" | "prompt" | "ios" | "macSafari" | "android" | "desktop";

let deferred: PromptEvent | null = null; // the browser offers installation once per page load
if (typeof window !== "undefined") {
  window.addEventListener("beforeinstallprompt", (e) => { e.preventDefault(); deferred = e as PromptEvent; });
}

/** Registers the service worker (production only) so the site can be installed as an app. */
export function PwaRegister() {
  useEffect(() => {
    if (process.env.NODE_ENV !== "production" || !("serviceWorker" in navigator)) return;
    navigator.serviceWorker.register("/sw.js", { scope: "/", updateViaCache: "none" }).catch(() => {});
  }, []);
  return null;
}

export function detect(): Platform {
  if (isStandalone()) return "installed"; // already running as the app
  if (deferred) return "prompt";
  const ua = navigator.userAgent;
  if (isIos()) return "ios";
  if (/Android/.test(ua)) return "android";
  if (/Macintosh/.test(ua) && /Version\/1[7-9]|Version\/[2-9]\d/.test(ua) && !/Chrome|Chromium|Edg/.test(ua)) return "macSafari";
  return "desktop";
}

/** The platform (null until known on the client) and the install action: the browser dialog where there is one. */
export function useInstall() {
  const [platform, setPlatform] = useState<Platform | null>(null);
  useEffect(() => {
    setPlatform(detect());
    const onPrompt = () => setPlatform(detect());
    const onInstalled = () => { deferred = null; setPlatform("installed"); };
    window.addEventListener("beforeinstallprompt", onPrompt);
    window.addEventListener("appinstalled", onInstalled);
    return () => { window.removeEventListener("beforeinstallprompt", onPrompt); window.removeEventListener("appinstalled", onInstalled); };
  }, []);
  const install = useCallback(async (): Promise<boolean> => {
    if (!deferred) return false;
    await deferred.prompt();
    const { outcome } = await deferred.userChoice;
    deferred = null;
    setPlatform(outcome === "accepted" ? "installed" : detect());
    return outcome === "accepted";
  }, []);
  return { platform, install };
}

/** "Install the app": the browser's own dialog where it exists (Android, Windows, Chrome / Edge on Mac),
 *  otherwise the steps for Safari on iPhone / iPad / Mac. Hidden inside the installed app. */
export function InstallApp({ className = "" }: { className?: string }) {
  const t = useT();
  const { platform, install } = useInstall();
  const [help, setHelp] = useState(false);

  if (platform !== "prompt" && platform !== "ios" && platform !== "macSafari") return null;
  return (
    <div className={`space-y-2 ${className}`}>
      <button type="button" onClick={() => (platform === "prompt" ? install() : setHelp((x) => !x))}
        className="inline-flex min-h-11 items-center gap-2 rounded-xl border border-line bg-surface px-3 text-sm font-semibold hover:border-brand hover:text-brand">
        <Icon name="smartphone" size={18} className="text-brand" />{t("pwa.install")}
      </button>
      {help && (platform === "ios" ? (
        <div className="max-w-sm rounded-xl bg-brand-50 p-3 text-sm" aria-live="polite">
          <ol className="list-decimal space-y-1.5 ps-5">
            {t("pwa.iosSteps").split("\n").slice(0, -1).map((s) => <li key={s}>{s}</li>)}
          </ol>
          <p className="mt-2 text-muted">{t("pwa.iosSteps").split("\n").at(-1)}</p>
        </div>
      ) : (
        <p className="max-w-sm rounded-xl bg-brand-50 p-3 text-sm" aria-live="polite">
          {t("pwa.macSteps")} <Link href="/app" className="link">{t("pwa.more")}</Link>
        </p>
      ))}
    </div>
  );
}

const VISITS = "konsilier.visits";
const BANNER = "konsilier.appBanner";   // "dismissed": the install banner is not shown again
const PUSH_BANNER = "konsilier.pushBanner";
// full-screen screens (a case, a chat) and the pages that already are about the app get no banner
const QUIET = ["/case/", "/chat/", "/app", "/share", "/account"];

function read(key: string): string | null {
  try { return localStorage.getItem(key); } catch { return null; }
}
function write(key: string, value: string) {
  try { localStorage.setItem(key, value); } catch {}
}

/**
 * A small banner on phones. In the browser, for a returning visitor (second visit on): «Установите приложение» →
 * /app. In the installed app: «Включить уведомления» once, until done or dismissed. Dismissal is remembered.
 */
export function AppBanner({ above = false }: { above?: boolean }) {
  const t = useT();
  const path = usePathname();
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

  if (!kind || QUIET.some((q) => path === q || path.startsWith(q))) return null;
  const dismiss = () => { write(kind === "push" ? PUSH_BANNER : BANNER, "dismissed"); setKind(null); };
  const enable = async () => {
    await enablePush().catch(() => null);
    dismiss();
  };
  return (
    <div role="region" aria-label={t(kind === "push" ? "push.title" : "pwa.bannerTitle")}
      className={`fixed inset-x-3 z-30 lg:hidden ${above ? "bottom-[calc(4.75rem+env(safe-area-inset-bottom))]" : "bottom-[calc(0.75rem+env(safe-area-inset-bottom))]"}`}>
      <div className="mx-auto flex max-w-lg items-center gap-3 rounded-2xl bg-surface p-3 shadow-[0_8px_30px_rgb(0_0_0/0.16)] ring-1 ring-black/[0.06]">
        <Icon name={kind === "push" ? "bell" : "smartphone"} size={22} className="shrink-0 text-brand" />
        <p className="min-w-0 flex-1 text-sm leading-snug">
          <span className="block font-semibold">{t(kind === "push" ? "push.short" : "pwa.bannerTitle")}</span>
          {kind === "install" && <span className="block text-muted">{t("pwa.bannerText")}</span>}
        </p>
        {kind === "install"
          ? <Link href="/app" onClick={dismiss} className="btn-primary min-h-9 shrink-0 px-3 text-sm">{t("pwa.bannerOpen")}</Link>
          : <button type="button" onClick={enable} className="btn-primary min-h-9 shrink-0 px-3 text-sm">{t("push.enable")}</button>}
        <button type="button" onClick={dismiss} aria-label={t("app.close")}
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-muted hover:bg-sand"><Icon name="x" size={18} /></button>
      </div>
    </div>
  );
}
