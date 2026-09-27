"use client";

import { Alert, Button } from "@/components/ui";
import { useT } from "@/lib/i18n";

export type EmergencyInfo = { message: string; numbers: { label: string; number: string }[] };

/** Shown before any intake when the story mentions immediate danger. Numbers come from the country pack. */
export function EmergencyPanel({ info, onContinue }: { info: EmergencyInfo; onContinue?: () => void }) {
  const t = useT();
  return (
    <Alert tone="danger" icon="phone" role="alert" title={t("emergency.title")}
      actions={onContinue && <Button variant="secondary" onClick={onContinue}>{t("emergency.continue")}</Button>}>
      <p>{info.message}</p>
      <ul className="mt-3 grid gap-2 sm:grid-cols-2">
        {info.numbers.map((n) => (
          <li key={n.number}>
            <a href={`tel:${n.number}`}
              className="flex min-h-11 items-center justify-between gap-3 rounded-xl bg-surface px-4 py-2 text-ink no-underline shadow-sm">
              <span className="text-sm">{n.label}</span>
              <span className="text-lg font-bold tabular-nums text-danger" dir="ltr">{n.number}</span>
            </a>
          </li>
        ))}
      </ul>
    </Alert>
  );
}
