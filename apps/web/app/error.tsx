"use client";

import { useEffect } from "react";
import { useT } from "@/lib/i18n";
import { reportClientError } from "@/lib/report";

export default function PageError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  const t = useT();
  useEffect(() => reportClientError(error), [error]);
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
