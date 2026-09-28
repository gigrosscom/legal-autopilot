"use client";

import { useEffect, useState } from "react";
import { Icon } from "@/components/ui";
import { useT } from "@/lib/i18n";

type PromptEvent = Event & { prompt: () => Promise<void>; userChoice: Promise<{ outcome: string }> };
type Platform = "prompt" | "ios" | "macSafari" | null;

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

function detect(): Platform {
  const standalone = matchMedia("(display-mode: standalone)").matches
    || (navigator as Navigator & { standalone?: boolean }).standalone === true;
  if (standalone) return null; // already running as the app
  if (deferred) return "prompt";
  const ua = navigator.userAgent;
  const ios = /iPhone|iPad|iPod/.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1);
  if (ios) return "ios";
  if (/Macintosh/.test(ua) && /Version\/1[7-9]|Version\/[2-9]\d/.test(ua) && !/Chrome|Chromium|Edg/.test(ua)) return "macSafari";
  return null;
}

/** "Install the app": the browser's own dialog where it exists (Android, Windows, Chrome / Edge on Mac),
 *  otherwise the steps for Safari on iPhone / iPad / Mac. Hidden inside the installed app. */
export function InstallApp({ className = "" }: { className?: string }) {
  const t = useT();
  const [platform, setPlatform] = useState<Platform>(null);
  const [help, setHelp] = useState(false);

  useEffect(() => {
    setPlatform(detect());
    const onPrompt = () => setPlatform(detect());
    const onInstalled = () => { deferred = null; setPlatform(null); };
    window.addEventListener("beforeinstallprompt", onPrompt);
    window.addEventListener("appinstalled", onInstalled);
    return () => { window.removeEventListener("beforeinstallprompt", onPrompt); window.removeEventListener("appinstalled", onInstalled); };
  }, []);

  if (!platform) return null;
  const install = async () => {
    if (platform === "prompt" && deferred) {
      await deferred.prompt();
      await deferred.userChoice;
      deferred = null;
      setPlatform(detect());
    } else setHelp((x) => !x);
  };
  return (
    <div className={`space-y-2 ${className}`}>
      <button type="button" onClick={install}
        className="inline-flex min-h-11 items-center gap-2 rounded-full border border-line bg-surface px-4 text-sm font-medium hover:border-action hover:text-brand">
        <Icon name="smartphone" size={18} className="text-brand" />{t("pwa.install")}
      </button>
      {help && (
        <p className="max-w-sm rounded-xl bg-brand-50 p-3 text-sm" aria-live="polite">
          {platform === "ios" ? t("pwa.iosSteps") : t("pwa.macSteps")}
        </p>
      )}
    </div>
  );
}
