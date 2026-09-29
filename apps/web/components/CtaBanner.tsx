"use client";

import { Button } from "@/components/ui";
import { useT } from "@/lib/i18n";

/** Closing call to action on information pages: describe the situation, or go to a lawyer. */
export function CtaBanner({ title, lead }: { title?: string; lead?: string }) {
  const t = useT();
  return (
    <section className="flex flex-col items-start gap-6 rounded-[28px] bg-sand p-7 md:flex-row md:items-center md:justify-between md:p-12">
      <div className="space-y-2">
        <h2 className="text-[28px] font-semibold leading-tight tracking-[-0.015em] md:text-[40px] md:tracking-[-0.018em]">{title ?? t("cta.title")}</h2>
        <p className="lead">{lead ?? t("cta.lead")}</p>
      </div>
      <div className="flex flex-wrap gap-3">
        <Button href="/start" size="lg" iconEnd="arrowRight">{t("cta.start")}</Button>
        <Button href="/lawyers" size="lg" variant="secondary" icon="lawyer">{t("cta.lawyer")}</Button>
      </div>
    </section>
  );
}
