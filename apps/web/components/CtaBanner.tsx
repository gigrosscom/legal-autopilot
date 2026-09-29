"use client";

import { Button } from "@/components/ui";
import { LAWYERS_PUBLIC } from "@/lib/features";
import { useT } from "@/lib/i18n";

/** Closing call to action on information pages: describe the situation (or go to a lawyer, when LAWYERS_PUBLIC). */
export function CtaBanner({ title, lead }: { title?: string; lead?: string }) {
  const t = useT();
  return (
    <section className="flex flex-col items-start gap-6 rounded-[28px] bg-sand p-7 md:flex-row md:items-center md:justify-between md:p-12">
      <div className="space-y-2">
        <h2 className="text-[28px] font-semibold leading-tight tracking-[-0.015em] md:text-[40px] md:tracking-[-0.018em]">{title ?? t("cta.title")}</h2>
        <p className="lead">{lead ?? t("cta.lead")}</p>
      </div>
      <div className="flex w-full flex-col gap-3 sm:w-auto sm:flex-row">
        <Button href="/start" size="lg" iconEnd="arrowRight" className="w-full sm:w-auto">{t("cta.start")}</Button>
        {LAWYERS_PUBLIC && <Button href="/lawyers" size="lg" variant="secondary" icon="lawyer" className="w-full sm:w-auto">{t("cta.lawyer")}</Button>}
      </div>
    </section>
  );
}
