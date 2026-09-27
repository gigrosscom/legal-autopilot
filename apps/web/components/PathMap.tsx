"use client";

import { Icon, type IconName } from "@/components/ui";
import { LevelBadge, type Level } from "@/components/LevelBadge";
import { useT } from "@/lib/i18n";

// Which coverage levels take part in each step (the case page shows the level of that particular case).
const STEPS: { key: string; icon: IconName; levels: Level[] }[] = [
  { key: "document", icon: "document", levels: ["verified", "universal"] },
  { key: "forum", icon: "building", levels: ["verified", "universal"] },
  { key: "deadline", icon: "clock", levels: ["verified", "universal"] },
  { key: "escalation", icon: "escalate", levels: ["verified", "universal"] },
  { key: "lawyer", icon: "lawyer", levels: ["lawyer"] },
];

/** The path of a case: document → body → deadline → escalation → lawyer. Coverage level shown on every step. */
export function PathMap() {
  const t = useT();
  return (
    <ol className="grid gap-3 md:grid-cols-5">
      {STEPS.map((s, i) => (
        <li key={s.key} className="card relative flex flex-col gap-3 p-4">
          <div className="flex items-center justify-between gap-2">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand-50 text-brand">
              <Icon name={s.icon} />
            </span>
            <span className="text-xs font-semibold text-muted">{i + 1} / {STEPS.length}</span>
          </div>
          <div className="space-y-1">
            <h3 className="font-semibold">{t(`path.${s.key}.title`)}</h3>
            <p className="text-sm text-muted">{t(`path.${s.key}.text`)}</p>
          </div>
          <div className="mt-auto flex flex-wrap gap-1.5">{s.levels.map((l) => <LevelBadge key={l} level={l} />)}</div>
        </li>
      ))}
    </ol>
  );
}
