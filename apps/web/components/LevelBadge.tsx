"use client";

import { Badge, Button, type Tone } from "@/components/ui";
import type { IconName } from "@/components/ui/Icon";
import { useT } from "@/lib/i18n";

export type Level = "pending" | "verified" | "scenario_draft" | "universal" | "lawyer" | "soon";

const LOOK: Record<Level, { tone: Tone; icon: IconName }> = {
  pending: { tone: "neutral", icon: "hourglass" },
  verified: { tone: "brand", icon: "shieldCheck" },
  scenario_draft: { tone: "draft", icon: "document" },
  universal: { tone: "info", icon: "map" },
  lawyer: { tone: "warning", icon: "lawyer" },
  soon: { tone: "neutral", icon: "hourglass" },
};

/** Coverage level of a case / country × branch. Label and meaning are always shown together somewhere nearby. */
export function LevelBadge({ level }: { level: Level }) {
  const t = useT();
  const look = LOOK[level] ?? LOOK.soon;
  return <Badge tone={look.tone} icon={look.icon}>{t(`level.${level}.label`)}</Badge>;
}

export function LevelExplainer({ level, stacked = false }: { level: Level; stacked?: boolean }) {
  const t = useT();
  return (
    <div className={`flex flex-col items-start gap-2 ${stacked ? "" : "sm:flex-row sm:gap-3"}`}>
      <LevelBadge level={level} />
      <p className="text-sm text-muted">{t(`level.${level}.desc`)}</p>
    </div>
  );
}

/** One action per coverage level: pick a ready situation / draft a document / find a lawyer. */
export function LevelAction({ level }: { level: "verified" | "universal" | "lawyer" }) {
  const t = useT();
  if (level === "lawyer") return <Button className="mt-auto" variant="secondary" href="/lawyers" icon="lawyer">{t("cta.lawyer")}</Button>;
  if (level === "verified") return <Button className="mt-auto" variant="secondary" href="/#situations" icon="checkCircle">{t("cta.pickSituation")}</Button>;
  return <Button className="mt-auto" variant="secondary" href="/start" icon="document">{t("cta.draftDocument")}</Button>;
}
