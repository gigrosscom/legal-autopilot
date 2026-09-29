"use client";

import { useCallback, useEffect, useState } from "react";
import { api, publicApi } from "@/lib/api";

/**
 * Web push on this device. The browser asks for permission only after a tap on «Включить уведомления»; the
 * subscription (the push service endpoint and keys) goes to the API, which then sends every notification here too.
 * iPhone / iPad: push works only in the app added to the home screen (iOS 16.4+), not in Safari's tabs.
 */
export type PushState =
  | "loading"
  | "unsupported"   // this browser has no web push
  | "needsInstall"  // iPhone / iPad in Safari: add to the home screen first
  | "off"           // the server has no push keys (not configured yet)
  | "denied"        // blocked in the browser / system settings
  | "ready"         // can be turned on
  | "on";

export function isStandalone(): boolean {
  return matchMedia("(display-mode: standalone)").matches
    || (navigator as Navigator & { standalone?: boolean }).standalone === true;
}

export function isIos(): boolean {
  const ua = navigator.userAgent;
  return /iPhone|iPad|iPod/.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1);
}

function supported(): boolean {
  return "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
}

function keyBytes(base64url: string): Uint8Array<ArrayBuffer> {
  const pad = "=".repeat((4 - (base64url.length % 4)) % 4);
  const raw = atob((base64url + pad).replace(/-/g, "+").replace(/_/g, "/"));
  const out = new Uint8Array(new ArrayBuffer(raw.length));
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
  return out;
}

let serverKey: Promise<string | null> | null = null;
function vapidKey(): Promise<string | null> {
  serverKey ??= publicApi<{ key: string }>("/v1/push/key").then((r) => r.key).catch(() => { serverKey = null; return null; });
  return serverKey;
}

/** The service worker, if one is (or soon will be) active; null in development, where none is registered. */
async function registration(): Promise<ServiceWorkerRegistration | null> {
  const reg = await navigator.serviceWorker.getRegistration("/");
  if (!reg) return null;
  return navigator.serviceWorker.ready;
}

async function current(): Promise<PushSubscription | null> {
  const reg = await registration();
  return reg ? reg.pushManager.getSubscription() : null;
}

function send(sub: PushSubscription) {
  return api("/v1/push/subscribe", { method: "POST", body: JSON.stringify({ ...sub.toJSON(), user_agent: navigator.userAgent }) });
}

export async function pushState(): Promise<PushState> {
  if (typeof window === "undefined") return "loading";
  if (isIos() && !isStandalone()) return "needsInstall";
  if (!supported()) return "unsupported";
  if (!(await vapidKey())) return "off";
  if (Notification.permission === "denied") return "denied";
  if (Notification.permission === "granted" && (await current())) return "on";
  return "ready";
}

/** Asks for permission (call it from a tap), subscribes and tells the API. Returns the new state. */
export async function enablePush(): Promise<PushState> {
  const key = await vapidKey();
  if (!key) return "off";
  const permission = await Notification.requestPermission();
  if (permission !== "granted") return permission === "denied" ? "denied" : "ready";
  let reg = await registration();
  if (!reg) {  // development: no worker registered on load
    await navigator.serviceWorker.register("/sw.js", { scope: "/", updateViaCache: "none" });
    reg = await navigator.serviceWorker.ready;
  }
  let sub = await reg.pushManager.getSubscription();
  sub ??= await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(key) });
  await send(sub);
  return "on";
}

export async function disablePush(): Promise<PushState> {
  const sub = await current();
  if (sub) {
    await api("/v1/push/unsubscribe", { method: "POST", body: JSON.stringify({ endpoint: sub.endpoint }) }).catch(() => {});
    await sub.unsubscribe().catch(() => false);
  }
  return pushState();
}

/** After signing in (the account may have changed): this device's subscription goes to the signed-in account. */
export async function resyncPush(): Promise<void> {
  if (typeof window === "undefined" || !supported() || Notification.permission !== "granted") return;
  const sub = await current().catch(() => null);
  if (sub) await send(sub).catch(() => {});
}

export function usePush() {
  const [state, setState] = useState<PushState>("loading");
  const [busy, setBusy] = useState(false);
  useEffect(() => { pushState().then(setState).catch(() => setState("unsupported")); }, []);
  const run = useCallback(async (fn: () => Promise<PushState>) => {
    setBusy(true);
    try { setState(await fn()); } catch { setState(await pushState().catch(() => "unsupported" as const)); } finally { setBusy(false); }
  }, []);
  return { state, busy, enable: () => run(enablePush), disable: () => run(disablePush) };
}
