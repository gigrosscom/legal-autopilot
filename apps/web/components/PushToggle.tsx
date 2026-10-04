"use client";

import Link from "next/link";
import { Button, Icon } from "@/components/ui";
import { useT } from "@/lib/i18n";
import { usePush } from "@/lib/push";

/**
 * «Включить уведомления» on this device. The browser's permission prompt opens only after the tap. `compact`: one
 * row for the bell panel, shown only while there is something to do; otherwise a card (profile, the app page).
 */
export function PushToggle({ compact = false, className = "" }: { compact?: boolean; className?: string }) {
  const t = useT();
  const { state, busy, enable, disable } = usePush();

  if (compact) {
    if (state === "ready") {
      return (
        <div className={`flex items-center gap-3 bg-sand px-5 py-3 ${className}`}>
          <Icon name="bell" size={20} className="shrink-0 text-brand" />
          <p className="flex-1 text-sm">{t("push.short")}</p>
          <button type="button" onClick={enable} disabled={busy}
            className="min-h-10 shrink-0 rounded-xl bg-action px-3 text-sm font-semibold text-white hover:bg-action-hover disabled:opacity-60">
            {t("push.enable")}
          </button>
        </div>
      );
    }
    if (state === "needsInstall") {
      return (
        <div className={`flex items-start gap-3 bg-sand px-5 py-3 text-sm ${className}`}>
          <Icon name="smartphone" size={20} className="mt-0.5 shrink-0 text-brand" />
          <p className="flex-1">{t("push.iosShort")} <Link href="/app" className="link">{t("push.howTo")}</Link></p>
        </div>
      );
    }
    return null;
  }

  if (state === "loading" || state === "off") return null;
  return (
    <section aria-labelledby="push-title" className={`card space-y-3 text-sm ${className}`}>
      <div className="flex items-start gap-3">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand"><Icon name="bell" /></span>
        <div className="space-y-1">
          <h2 id="push-title" className="font-semibold">{t("push.title")}</h2>
          <p className="text-muted">{t("push.lead")}</p>
        </div>
      </div>
      {state === "on" && (
        <div className="flex flex-wrap items-center gap-3">
          <p className="flex items-center gap-2 font-medium text-success" role="status"><Icon name="checkCircle" size={18} />{t("push.on")}</p>
          <button type="button" onClick={disable} disabled={busy} className="min-h-10 text-muted underline hover:text-ink">{t("push.disable")}</button>
        </div>
      )}
      {state === "ready" && <Button onClick={enable} disabled={busy} icon={busy ? "spinner" : "bell"}>{t("push.enable")}</Button>}
      {state === "denied" && <p className="text-warning" role="status">{t("push.denied")}</p>}
      {state === "needsInstall" && (
        <p className="text-muted">{t("push.ios")} <Link href="/app" className="link">{t("push.howTo")}</Link></p>
      )}
      {state === "unsupported" && <p className="text-muted">{t("push.unsupported")}</p>}
    </section>
  );
}
