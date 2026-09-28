"use client";

import { Button } from "@/components/ui";
import { useT } from "@/lib/i18n";

/** Closing call to action on information pages: a centred grey tile — describe the situation, or go to a lawyer. */
export function CtaBanner({ title, lead }: { title?: string; lead?: string }) {
  const t = useT();
  return (
    <section className="tile flex flex-col items-center gap-6 text-center">
      <div className="max-w-2xl space-y-3">
        <h2 className="text-[32px] font-semibold leading-[1.1] tracking-[-0.015em] text-balance text-ink md:text-[48px]">{title ?? t("cta.title")}</h2>
        <p className="text-[17px] text-muted text-pretty md:text-[21px]">{lead ?? t("cta.lead")}</p>
      </div>
      <div className="flex flex-wrap justify-center gap-3">
        <Button href="/start" size="lg">{t("cta.start")}</Button>
        <Button href="/lawyers" size="lg" variant="secondary">{t("cta.lawyer")}</Button>
      </div>
    </section>
  );
}
