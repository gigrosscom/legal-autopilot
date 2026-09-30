"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useAuthError } from "@/components/CodeForm";
import { api, type SignedIn } from "@/lib/api";
import { useLang, useT } from "@/lib/i18n";

/* «Войти через Google» and «Войти через Apple»: the provider's own window (a popup, no redirect, so the installed
   app works too) hands the page an ID token; the API checks it and signs in like the e-mail code does.
   Before the button is shown the page asks the API for a one-time nonce (bound to this device's session) and gives
   it to the provider, so the token names this very sign-in. */

const GSI_SRC = "https://accounts.google.com/gsi/client";
const APPLE_SRC = "https://appleid.cdn-apple.com/appleauth/static/jsapi/appleid/1/en_US/appleid.auth.js";
const REFRESH_MS = 25 * 60 * 1000;  // the API keeps a nonce 30 minutes
const MAX_W = 400;  // Google draws its button at most 400 px wide; Apple's matches it

type GoogleId = {
  initialize: (o: Record<string, unknown>) => void;
  renderButton: (el: HTMLElement, o: Record<string, unknown>) => void;
};
type AppleAuth = {
  init: (o: Record<string, unknown>) => void;
  signIn: () => Promise<{ authorization: { id_token: string }; user?: { name?: { firstName?: string; lastName?: string } } }>;
};
declare global {
  interface Window {
    google?: { accounts: { id: GoogleId } };
    AppleID?: { auth: AppleAuth };
  }
}

const loading = new Map<string, Promise<void>>();
function loadScript(src: string): Promise<void> {
  let p = loading.get(src);
  if (!p) {
    p = new Promise<void>((resolve, reject) => {
      const s = document.createElement("script");
      s.src = src; s.async = true;
      s.onload = () => resolve();
      s.onerror = () => { loading.delete(src); reject(new Error("script")); };
      document.head.appendChild(s);
    });
    loading.set(src, p);
  }
  return p;
}

export function ProviderSignIn({ google, apple, onDone }: { google: boolean; apple: boolean; onDone: (r: SignedIn) => void }) {
  const [error, setError] = useState<string | null>(null);
  if (!google && !apple) return null;
  return (
    <div className="mx-auto w-full space-y-3" style={{ maxWidth: MAX_W }}>
      {google && <GoogleButton onDone={onDone} onError={setError} />}
      {apple && <AppleButton onDone={onDone} onError={setError} />}
      {error && <p role="alert" className="text-center text-[15px] text-danger">{error}</p>}
    </div>
  );
}

type Props = { onDone: (r: SignedIn) => void; onError: (e: string | null) => void };

function GoogleButton({ onDone, onError }: Props) {
  const t = useT();
  const { lang } = useLang();
  const authError = useAuthError();
  const box = useRef<HTMLDivElement>(null);
  const nonce = useRef("");
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const cb = useRef({ onDone, onError, authError, t });
  useEffect(() => { cb.current = { onDone, onError, authError, t }; });

  // Quiet while preparing: a failure shows only when the person presses the button.
  const prepare = useCallback(async (loud = false) => {
    try {
      const [start] = await Promise.all([
        api<{ nonce: string; client_id: string }>("/v1/auth/google/start", { method: "POST" }),
        loadScript(GSI_SRC),
      ]);
      const gid = window.google?.accounts.id;
      if (!gid || !box.current) throw new Error("gsi");
      nonce.current = start.nonce;
      gid.initialize({
        client_id: start.client_id,
        nonce: start.nonce,
        auto_select: false,
        itp_support: true,
        callback: async (resp: { credential?: string }) => {
          if (!resp.credential) return;
          const { onDone, onError, authError } = cb.current;
          setBusy(true); onError(null);
          try {
            onDone(await api<SignedIn>("/v1/auth/google/verify", {
              method: "POST", body: JSON.stringify({ credential: resp.credential, nonce: nonce.current }),
            }));
          } catch (err) {
            onError(authError(err));
            prepare();  // a fresh nonce for the next try
          } finally { setBusy(false); }
        },
      });
      const width = Math.min(MAX_W, Math.max(200, Math.floor(box.current.getBoundingClientRect().width || MAX_W)));
      box.current.replaceChildren();
      gid.renderButton(box.current, {
        type: "standard", theme: "outline", size: "large", shape: "pill", text: "signin_with",
        logo_alignment: "center", width, locale: lang,
      });
      setReady(true);
    } catch (err) {
      if (!loud) return;
      const { onError, authError, t } = cb.current;
      onError(err instanceof Error && (err.message === "script" || err.message === "gsi")
        ? t("account.google.failed") : authError(err));
    }
  }, [lang]);

  useEffect(() => {
    prepare();
    const id = setInterval(() => prepare(), REFRESH_MS);
    return () => clearInterval(id);
  }, [prepare]);

  return (
    <div className="relative min-h-12">
      {/* Google draws its own branded button here; until then (or if its script is blocked) a look-alike stands in */}
      <div ref={box} className={`flex justify-center ${busy ? "pointer-events-none opacity-60" : ""}`} aria-busy={busy} />
      {!ready && (
        <button type="button" onClick={() => prepare(true)}
          className="absolute inset-0 flex min-h-12 items-center justify-center gap-3 rounded-full border border-[#dadce0] bg-white px-4 text-[17px] font-semibold text-[#1f1f1f]">
          <GoogleLogo /> {t("account.google.button")}
        </button>
      )}
    </div>
  );
}

function AppleButton({ onDone, onError }: Props) {
  const t = useT();
  const authError = useAuthError();
  const nonce = useRef("");
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const failed = useRef<(err: unknown) => void>(() => {});
  useEffect(() => { failed.current = (err) => onError(authError(err)); });

  // Quiet while preparing: a failure shows only when the person presses the button.
  const prepare = useCallback(async (loud = false): Promise<boolean> => {
    try {
      const [start] = await Promise.all([
        api<{ nonce: string; nonce_sha256: string; client_id: string; redirect_uri: string }>("/v1/auth/apple/start", { method: "POST" }),
        loadScript(APPLE_SRC),
      ]);
      const auth = window.AppleID?.auth;
      if (!auth) throw new Error("apple");
      nonce.current = start.nonce;
      // Apple gets SHA-256 of our nonce and puts that hash into the token; the API hashes the raw nonce to compare
      auth.init({ clientId: start.client_id, scope: "name email", redirectURI: start.redirect_uri,
        nonce: start.nonce_sha256, usePopup: true });
      setReady(true);
      return true;
    } catch (err) {
      if (!loud) return false;
      if (err instanceof Error && (err.message === "script" || err.message === "apple")) onError(t("account.apple.failed"));
      else failed.current(err);
      return false;
    }
  }, [onError, t]);

  useEffect(() => {
    prepare();
    const id = setInterval(() => prepare(), REFRESH_MS);
    return () => clearInterval(id);
  }, [prepare]);

  const signIn = async () => {
    const auth = window.AppleID?.auth;
    if (!auth || !ready) { await prepare(true); return; }
    setBusy(true); onError(null);
    let res: Awaited<ReturnType<AppleAuth["signIn"]>>;
    try {
      res = await auth.signIn();  // opens Apple's window right away: this click is the user gesture
    } catch (err) {
      const code = (err as { error?: string } | null)?.error;
      if (code !== "popup_closed_by_user" && code !== "user_cancelled_authorize") onError(t("account.apple.failed"));
      setBusy(false);
      return;
    }
    try {
      const n = res.user?.name;
      const name = [n?.firstName, n?.lastName].filter(Boolean).join(" ") || undefined;
      onDone(await api<SignedIn>("/v1/auth/apple/verify", {
        method: "POST", body: JSON.stringify({ id_token: res.authorization.id_token, nonce: nonce.current, name }),
      }));
    } catch (err) {
      failed.current(err);
    } finally {
      setBusy(false);
      prepare();  // a nonce is good for one sign-in
    }
  };

  return (
    <button type="button" onClick={signIn} disabled={busy} aria-busy={busy}
      className="flex min-h-12 w-full items-center justify-center gap-2.5 rounded-full bg-black px-4 text-[17px] font-semibold text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60">
      <AppleLogo /> {t("account.apple.button")}
    </button>
  );
}

function GoogleLogo() {
  return (
    <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden focusable="false">
      <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z" />
      <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z" />
      <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z" />
      <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z" />
    </svg>
  );
}

function AppleLogo() {
  return (
    <svg width="17" height="20" viewBox="0 0 814 1000" aria-hidden focusable="false" fill="currentColor">
      <path d="M788.1 340.9c-5.8 4.5-108.2 62.2-108.2 190.5 0 148.4 130.3 200.9 134.2 202.2-.6 3.2-20.7 71.9-68.7 141.9-42.8 61.6-87.5 123.1-155.5 123.1s-85.5-39.5-164-39.5c-76.5 0-103.7 40.8-165.9 40.8s-105.6-57-155.5-127C46.7 790.7 0 663 0 541.8c0-194.4 126.4-297.5 250.8-297.5 66.1 0 121.2 43.4 162.7 43.4 39.5 0 101.1-46 176.3-46 28.5 0 130.9 2.6 198.3 99.2zm-234-181.5c31.1-36.9 53.1-88.1 53.1-139.3 0-7.1-.6-14.3-1.9-20.1-50.6 1.9-110.8 33.7-147.1 75.8-28.5 32.4-55.1 83.6-55.1 135.5 0 7.8 1.3 15.6 1.9 18.1 3.2.6 8.4 1.3 13.6 1.3 45.4 0 102.5-30.4 135.5-71.3z" />
    </svg>
  );
}
