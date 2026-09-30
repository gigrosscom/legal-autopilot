"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui";
import { ApiError, api, errorText, type SignedIn } from "@/lib/api";
import { useLang, useT } from "@/lib/i18n";
import { NcaLayerError } from "@/lib/ncalayer";

/** A sign-in error in words: the API's code (account.errors.*), NCALayer's reason, or the general text. */
export function useAuthError() {
  const t = useT();
  return (e: unknown): string => {
    if (e instanceof ApiError && e.code) {
      const key = `account.errors.${e.code}`;
      const text = t(key);
      if (text !== key) return text;
    }
    if (e instanceof NcaLayerError) return t(`account.ecp.${e.kind}`);
    return errorText(e);
  };
}

/** Confirm an e-mail or a phone by a one-time code: the address, «Получить код», the code, «Подтвердить».
 *  `wide`: full-width buttons and no top rule, for the payment window on a phone. */
/** `onSendFailed`: the code could not be sent (the channel is down) — the caller may go on without it (payment does). */
export function CodeForm({ kind, onDone, onSendFailed, wide = false }: {
  kind: "email" | "phone"; onDone: (r: SignedIn) => void; onSendFailed?: () => void; wide?: boolean;
}) {
  const t = useT();
  const { lang } = useLang();
  const authError = useAuthError();
  const [target, setTarget] = useState(kind === "phone" ? "+7 " : "");
  const [code, setCode] = useState("");
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const btn = "min-h-12 w-full";
  const [wait, setWait] = useState(0);  // seconds until the code can be sent again
  const tried = useRef("");             // the code last checked, so a typed code is checked once
  useEffect(() => {
    if (wait <= 0) return;
    const id = setTimeout(() => setWait((w) => w - 1), 1000);
    return () => clearTimeout(id);
  }, [wait]);

  const send = async (e?: React.FormEvent) => {
    e?.preventDefault();
    setBusy(true); setError(null);
    try {
      await api(`/v1/auth/${kind}/start`, { method: "POST", body: JSON.stringify({ target, language: lang }) });
      setSent(true); setWait(60); setCode(""); tried.current = "";
    } catch (err) {
      if (onSendFailed && err instanceof ApiError && err.code === "send_failed") { onSendFailed(); return; }
      setError(authError(err));
    } finally { setBusy(false); }
  };
  const verify = async (e?: React.FormEvent) => {
    e?.preventDefault();
    tried.current = code;
    setBusy(true); setError(null);
    try {
      onDone(await api<SignedIn>(`/v1/auth/${kind}/verify`, { method: "POST", body: JSON.stringify({ target, code }) }));
    } catch (err) { setError(authError(err)); } finally { setBusy(false); }
  };

  // as in the messengers: the six digits in, the code is checked at once
  useEffect(() => { if (sent && code.length === 6 && tried.current !== code && !busy) verify(); });

  return (
    <div className={`enter space-y-3 ${wide ? "" : "border-t border-line pt-3"}`}>
      {!sent ? (
        <form onSubmit={send} className="space-y-3">
          <label className="block space-y-1 text-sm">
            <span className="font-medium">{t(`account.${kind}.label`)}</span>
            <input className="input min-h-12 text-[17px]" dir="ltr" required value={target} onChange={(e) => setTarget(e.target.value)}
              type={kind === "email" ? "email" : "tel"} autoComplete={kind === "email" ? "email" : "tel"} autoFocus={wide}
              inputMode={kind === "email" ? "email" : "tel"} placeholder={kind === "email" ? "name@mail.kz" : "+7 701 123 45 67"} />
          </label>
          <Button className={btn} disabled={busy || target.replace(/\D/g, "").length < (kind === "phone" ? 10 : 0) || target.trim().length < 5}
            icon={busy ? "spinner" : "send"}>{t("account.sendCode")}</Button>
        </form>
      ) : (
        <form onSubmit={verify} className="space-y-3">
          <p className="text-[15px] text-ink-soft">{t(`account.${kind}.sent`, { target })}</p>
          <label className="block rounded-2xl border border-line bg-sand px-4 pt-2.5 pb-2 focus-within:border-brand">
            <span className="block text-xs text-muted">{t("account.codeLabel")}</span>
            <input className="w-full border-0 bg-transparent p-0 text-[26px] font-medium tracking-[0.35em] text-ink outline-none"
              dir="ltr" required inputMode="numeric" autoFocus autoComplete="one-time-code" maxLength={6} pattern="\d{6}"
              value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} style={{ outline: "none" }} />
          </label>
          <Button className={btn} disabled={busy || code.length !== 6} icon={busy ? "spinner" : undefined}>{busy ? "" : t("account.confirm")}</Button>
          <div className="flex flex-col items-center gap-1 text-sm">
            <button type="button" disabled={busy || wait > 0} onClick={() => send()}
              className="min-h-10 font-semibold text-ink disabled:font-normal disabled:text-muted">
              {wait > 0 ? t("account.resendIn", { n: wait }) : t("account.resend")}
            </button>
            <button type="button" className="min-h-10 text-muted hover:text-ink" onClick={() => { setSent(false); setCode(""); }}>{t("account.changeTarget")}</button>
          </div>
        </form>
      )}
      {error && <p role="alert" className="text-sm text-danger">{error}</p>}
    </div>
  );
}
