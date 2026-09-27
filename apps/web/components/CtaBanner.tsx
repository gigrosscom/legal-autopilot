"use client";

import { Button } from "@/components/ui";
import { useT } from "@/lib/i18n";

/** Closing call to action on information pages: describe the situation, or go to a lawyer. */
export function CtaBanner({ title, lead }: { title?: string; lead?: string }) {
  const t = useT();
  return (
    <section className="card flex flex-col items-start gap-4 bg-brand-50 p-6 md:flex-row md:items-center md:justify-between md:p-8">
      <div className="space-y-1">
        <h2 className="text-xl font-bold">{title ?? t("cta.title")}</h2>
        <p className="text-muted">{lead ?? t("cta.lead")}</p>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button href="/start" size="lg" iconEnd="arrowRight">{t("cta.start")}</Button>
        <Button href="/lawyers" size="lg" variant="secondary" icon="lawyer">{t("cta.lawyer")}</Button>
      </div>
    </section>
  );
}
