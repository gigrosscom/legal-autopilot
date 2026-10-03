"use client";

import { COLUMNS } from "@/components/CaseBoard";
import { useT } from "@/lib/i18n";

/** Where the case is on the board: same columns as the kanban, so the user sees one consistent path. */
export function StageProgress({ stage }: { stage: string }) {
  const t = useT();
  const idx = Math.max(0, COLUMNS.indexOf(stage as (typeof COLUMNS)[number]));
  return (
    <div className="space-y-1.5">
      <p className="text-xs text-muted">
        {t("board.stepOf", { n: idx + 1, total: COLUMNS.length })}: <span className="font-semibold text-ink">{t(`board.${COLUMNS[idx]}`)}</span>
      </p>
      <ol className="flex gap-1" aria-hidden>
        {COLUMNS.map((col, i) => (
          <li key={col} className={`h-1.5 flex-1 rounded-full ${i <= idx ? "bg-brand" : "bg-line"}`} />
        ))}
      </ol>
    </div>
  );
}
