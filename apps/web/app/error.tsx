"use client";

import { useEffect, useState } from "react";
import { useT } from "@/lib/i18n";
import { reportClientError } from "@/lib/report";

// React loses track of DOM nodes that a browser extension (translator, grammar checker,
// password manager) has moved or replaced. The data is safe on the server, so the page just
// needs to be rendered again from scratch.
const DOM_DESYNC = /removeChild|insertBefore|not a child of this node|NotFoundError/i;
const RETRY_KEY = "konsilier.autoRetryAt";

export default function PageError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  const t = useT();
  const [retrying, setRetrying] = useState(() => shouldAutoRetry(error));
  useEffect(() => reportClientError(error), [error]);
  useEffect(() => {
    if (!retrying) return;
    try {
      sessionStorage.setItem(RETRY_KEY, String(Date.now()));
    } catch {}
    reset();
    setRetrying(false);
  }, [retrying, reset]);
  if (retrying) return null;
  return (
    <div className="card mx-auto max-w-lg space-y-3 text-center">
      <h1 className="text-xl font-bold">{t("errors.title")}</h1>
      <p className="text-sm text-muted">{t("errors.saved")}</p>
      <p className="text-xs text-muted">{t("errors.translate")}</p>
      <div className="flex justify-center gap-2">
        <button className="btn-primary" onClick={() => window.location.reload()}>{t("errors.reload")}</button>
        <button className="btn-ghost" onClick={() => reset()}>{t("errors.retry")}</button>
      </div>
    </div>
  );
}

function shouldAutoRetry(error: Error): boolean {
  if (!DOM_DESYNC.test(`${error?.name} ${error?.message}`)) return false;
  try {
    // At most one silent retry per 30 s, so a real bug still shows the error screen.
    return Date.now() - Number(sessionStorage.getItem(RETRY_KEY) || 0) > 30_000;
  } catch {
    return false;
  }
}
