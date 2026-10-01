"use client";

import { usePathname } from "next/navigation";
import { useEffect, useRef } from "react";

const BUILD = process.env.NEXT_PUBLIC_BUILD_ID;
const EVERY = 5 * 60_000;

/** Nothing the person typed is on the page (a message, a form field): reloading now loses nothing. */
function idle(): boolean {
  const fields = document.querySelectorAll<HTMLInputElement | HTMLTextAreaElement>(
    "textarea, input:not([type=hidden]):not([type=checkbox]):not([type=radio]):not([type=file]):not([type=submit]):not([type=button])");
  for (const f of fields) if (f.value.trim()) return false;
  return true;  // an empty focused box (the home page's) loses nothing
}

/** Owner 01.10: a tab (or an installed app) opened before a deploy keeps running the old build — client navigation
 * never reloads the code. The build id is checked on return to the tab, on every navigation and every 5 minutes;
 * a newer build reloads the page at once when nothing typed would be lost, otherwise at the next navigation. */
export function VersionWatch() {
  const path = usePathname();
  const stale = useRef(false);
  const first = useRef(true);

  useEffect(() => {
    if (!BUILD || process.env.NODE_ENV !== "production") return;
    let busy = false;
    const check = async () => {
      if (busy || document.visibilityState !== "visible") return;
      busy = true;
      try {
        const r = await fetch("/version.json", { cache: "no-store" });
        const { id } = (await r.json()) as { id: string | null };
        if (id && id !== BUILD) {
          stale.current = true;
          if (idle()) window.location.reload();
        }
      } catch { /* offline: try later */ } finally { busy = false; }
    };
    check();
    const timer = setInterval(check, EVERY);
    document.addEventListener("visibilitychange", check);
    window.addEventListener("focus", check);
    return () => { clearInterval(timer); document.removeEventListener("visibilitychange", check); window.removeEventListener("focus", check); };
  }, []);

  // every navigation: an old build is replaced by a full load of the page the person is going to
  useEffect(() => {
    if (first.current) { first.current = false; return; }
    if (stale.current) { window.location.reload(); return; }
    fetch("/version.json", { cache: "no-store" }).then((r) => r.json()).then(({ id }: { id: string | null }) => {
      if (id && BUILD && id !== BUILD) { stale.current = true; if (idle()) window.location.reload(); }
    }).catch(() => {});
  }, [path]);

  return null;
}
