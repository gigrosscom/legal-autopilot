"use client";

import { useState } from "react";
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
export function CodeForm({ kind, onDone, wide = false }: { kind: "email" | "phone"; onDone: (r: SignedIn) => void; wide?: boolean }) {
  const t = useT();
  const { lang } = useLang();
  const authError = useAuthError();
  const [target, setTarget] = useState(kind === "phone" ? "+7 " : "");
  const [code, setCode] = useState("");
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const btn = wide ? "min-h-12 w-full" : undefined;

  const send = async (e?: React.FormEvent) => {
    e?.preventDefault();
    setBusy(true); setError(null);
    try {
      await api(`/v1/auth/${kind}/start`, { method: "POST", body: JSON.stringify({ target, language: lang }) });
      setSent(true);
    } catch (err) { setError(authError(err)); } finally { setBusy(false); }
  };
  const verify = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      onDone(await api<SignedIn>(`/v1/auth/${kind}/verify`, { method: "POST", body: JSON.stringify({ target, code }) }));
    } catch (err) { setError(authError(err)); } finally { setBusy(false); }
  };

  return (
    <div className={`enter space-y-3 ${wide ? "" : "border-t border-line pt-3"}`}>
      {!sent ? (
        <form onSubmit={send} className="space-y-3">
          <label className="block space-y-1 text-sm">
            <span className="font-medium">{t(`account.${kind}.label`)}</span>
            <input className="input" dir="ltr" required value={target} onChange={(e) => setTarget(e.target.value)}
              type={kind === "email" ? "email" : "tel"} autoComplete={kind === "email" ? "email" : "tel"} autoFocus={wide}
              inputMode={kind === "email" ? "email" : "tel"} placeholder={kind === "email" ? "name@mail.kz" : "+7 701 123 45 67"} />
          </label>
          <Button className={btn} disabled={busy || target.replace(/\D/g, "").length < (kind === "phone" ? 10 : 0) || target.trim().length < 5}
            icon={busy ? "spinner" : "send"}>{t("account.sendCode")}</Button>
        </form>
      ) : (
        <form onSubmit={verify} className="space-y-3">
          <p className="text-sm text-muted">{t(`account.${kind}.sent`, { target })}</p>
          <label className="block space-y-1 text-sm">
            <span className="font-medium">{t("account.codeLabel")}</span>
            <input className="input max-w-40 text-lg tracking-[0.3em]" dir="ltr" required inputMode="numeric" autoFocus={wide}
              autoComplete="one-time-code" maxLength={6} pattern="\d{6}" value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} />
          </label>
          <div className="flex flex-wrap gap-2">
            <Button className={btn} disabled={busy || code.length !== 6} icon={busy ? "spinner" : "check"}>{t("account.confirm")}</Button>
            <button type="button" className={`btn-ghost ${wide ? "w-full" : ""}`} onClick={() => { setSent(false); setCode(""); }}>{t("account.changeTarget")}</button>
          </div>
        </form>
      )}
      {error && <p role="alert" className="text-sm text-danger">{error}</p>}
    </div>
  );
}
