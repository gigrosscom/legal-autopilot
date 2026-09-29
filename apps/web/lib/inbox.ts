"use client";

import { useSyncExternalStore } from "react";
import { api } from "@/lib/api";

/** One message of the site inbox (the bell): deadline reminders, payment, document ready, desk replies. */
export type InboxItem = {
  id: number;
  case_id: string | null;
  kind: string;
  text: string;
  created_at: string;
  read_at: string | null;
};
export type Inbox = { items: InboxItem[]; unread: number };

const POLL_MS = 60_000;

// One poller for the whole page, however many bells are mounted (sidebar, top bar, case screen).
let state: Inbox | null = null;
const listeners = new Set<() => void>();
let timer: ReturnType<typeof setInterval> | null = null;
let loading = false;

function emit(next: Inbox) {
  state = next;
  listeners.forEach((l) => l());
}

function hasToken(): boolean {
  try { return !!localStorage.getItem("konsilier.token"); } catch { return false; }
}

/** Reloads the inbox. A visitor without an account yet has no inbox: no request, so no account is made for it. */
export async function refreshInbox() {
  if (loading || !hasToken()) return;
  loading = true;
  try {
    emit(await api<Inbox>("/v1/notifications"));
  } catch {
    // offline or the API is away: keep what is shown, the next poll tries again
  } finally {
    loading = false;
  }
}

/** Marks notifications read at once on screen, then on the server (its unread count wins). */
export async function markRead(body: { ids: number[] } | { all: true }) {
  const hit = (n: InboxItem) => !n.read_at && ("all" in body || body.ids.includes(n.id));
  if (state) {
    const now = new Date().toISOString();
    const items = state.items.map((n) => (hit(n) ? { ...n, read_at: now } : n));
    emit({ items, unread: Math.max(0, state.unread - state.items.filter(hit).length) });
  }
  try {
    const r = await api<{ unread: number }>("/v1/notifications/read", { method: "POST", body: JSON.stringify(body) });
    if (state) emit({ ...state, unread: r.unread });
  } catch {}
}

function onVisibility() {
  if (document.visibilityState === "visible") {
    refreshInbox();
    timer ??= setInterval(refreshInbox, POLL_MS);
  } else if (timer) {
    clearInterval(timer);
    timer = null;
  }
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  if (listeners.size === 1) {
    document.addEventListener("visibilitychange", onVisibility);
    onVisibility();  // polls every minute only while the page is visible
  }
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0) {
      document.removeEventListener("visibilitychange", onVisibility);
      if (timer) clearInterval(timer);
      timer = null;
    }
  };
}

export function useInbox(): Inbox | null {
  return useSyncExternalStore(subscribe, () => state, () => null);
}
