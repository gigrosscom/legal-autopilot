"use client";

import { Badge } from "@/components/ui";
import { useLang, type Lang } from "@/lib/i18n";

// «Бета» mark of experimental scenarios (EXPERIMENTAL_SCENARIOS): kept here so the shared dictionaries stay untouched.
const LABEL: Record<Lang, string> = { ru: "Бета", kk: "Бета", en: "Beta", tr: "Beta", ar: "تجريبي" };

/** Shown on a case of a beta scenario: the mark and the scenario's own disclaimer (no guarantee of the result). */
export function BetaNotice({ disclaimer }: { disclaimer: string | null | undefined }) {
  const { lang } = useLang();
  return (
    <p className="flex items-start gap-2 rounded-2xl bg-info-50 px-3 py-2 text-xs text-info" data-testid="beta-notice">
      <Badge tone="info">{LABEL[lang] ?? LABEL.ru}</Badge>
      {disclaimer && <span>{disclaimer}</span>}
    </p>
  );
}
