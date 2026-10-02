"use client";

import { usePathname, useRouter } from "next/navigation";
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

/** The chat, a case and the way into them are never reloaded under the person (owner 02.10, «чат слетел»): sending
 *  the first message turns /chat into /chat/<id> while the answer streams in, and /start hands the message over to
 *  the chat in memory — a reload there lost the answer or the message. A newer build waits for the next page. */
const KEEP = /^\/(chat|case|start)(\/|$)/;
const safe = (path: string) => !KEEP.test(path) && idle();

/** iOS closes a Home-screen app in the background and starts it again at its start URL (/?source=app): the person
 *  was in a chat and found the home page («чат слетел», owner 02.10). The last chat or case is kept and reopened
 *  when the app starts again within RESUME_MS. */
const RESUME = "konsilier.resume";
const RESUME_MS = 6 * 3600_000;
const RESUMABLE = /^\/(chat|case)\/[^/]+$/;

/** Owner 01.10: a tab (or an installed app) opened before a deploy keeps running the old build — client navigation
 * never reloads the code. The build id is checked on return to the tab, on every navigation and every 5 minutes;
 * a newer build reloads the page at once when nothing typed would be lost, otherwise at the next navigation —
 * never in the chat or a case (see KEEP). */
export function VersionWatch() {
  const path = usePathname();
  const stale = useRef(false);
  const first = useRef(true);
  const router = useRouter();

  useEffect(() => {
    try {
      if (RESUMABLE.test(path) && path !== "/case/demo") localStorage.setItem(RESUME, JSON.stringify({ path, at: Date.now() }));
      else if (path !== "/") localStorage.removeItem(RESUME);  // moved on elsewhere in the app: start there next time
    } catch {}
  }, [path]);

  useEffect(() => {
    try {
      if (window.location.pathname !== "/" || new URLSearchParams(window.location.search).get("source") !== "app") return;
      const saved = JSON.parse(localStorage.getItem(RESUME) || "null") as { path?: string; at?: number } | null;
      if (saved?.path && RESUMABLE.test(saved.path) && Date.now() - (saved.at ?? 0) < RESUME_MS) router.replace(saved.path);
    } catch {}
  }, [router]);

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
          if (safe(window.location.pathname)) window.location.reload();
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
    if (KEEP.test(path)) return;  // arriving in the chat or a case: the build is replaced on the way out
    if (stale.current) { window.location.reload(); return; }
    fetch("/version.json", { cache: "no-store" }).then((r) => r.json()).then(({ id }: { id: string | null }) => {
      if (id && BUILD && id !== BUILD) { stale.current = true; if (safe(path)) window.location.reload(); }
    }).catch(() => {});
  }, [path]);

  return null;
}
