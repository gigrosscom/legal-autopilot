"use client";

import { Icon } from "@/components/ui";
import type { Roadmap, RoadmapStep } from "@/lib/api";
import { useT } from "@/lib/i18n";

const fmt = (iso: string | null) => (iso ? new Date(iso + "T00:00:00").toLocaleDateString("ru-RU") : "");

const DOT: Record<RoadmapStep["status"], string> = {
  done: "bg-brand text-white border-brand",
  current: "bg-surface text-brand border-brand ring-4 ring-brand/15",
  upcoming: "bg-surface text-muted border-line",
  skipped: "bg-sand text-muted border-line",
};

export default function RoadmapView({ roadmap }: { roadmap: Roadmap }) {
  const t = useT();
  return (
    <div className="card space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <h2 className="font-semibold">{t("roadmap.title")}</h2>
        {(roadmap.best_case_on || roadmap.worst_case_on) && (
          <div className="flex flex-wrap gap-2 text-xs">
            {roadmap.best_case_on && (
              <span className="chip bg-brand-50 text-brand-dark">{t("roadmap.best")}: {fmt(roadmap.best_case_on)}</span>
            )}
            {roadmap.worst_case_on && roadmap.worst_case_on !== roadmap.best_case_on && (
              <span className="chip">
                {t("roadmap.worst")}: {fmt(roadmap.worst_case_on)}
                {roadmap.open_ended_after_worst ? `, ${t("roadmap.openEnded")}` : ""}
              </span>
            )}
          </div>
        )}
      </div>
      <ol className="relative space-y-4">
        {roadmap.steps.map((s, i) => (
          <li key={s.key} className={`relative flex gap-3 ${s.status === "skipped" ? "opacity-50" : ""}`}>
            {i < roadmap.steps.length - 1 && (
              <span className={`absolute start-[13px] top-7 h-[calc(100%-4px)] w-0.5 ${s.status === "done" ? "bg-brand" : "bg-line"}`} />
            )}
            <span className={`z-10 flex h-7 w-7 shrink-0 items-center justify-center rounded-full border-2 text-xs font-semibold ${DOT[s.status]}`}>
              {s.status === "done" ? <Icon name="check" size={14} /> : i + 1}
            </span>
            <div className="min-w-0 flex-1 pb-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className={`font-medium ${s.status === "skipped" ? "line-through" : ""}`}>{s.title}</span>
                <span className={`chip ${s.status === "current" ? "bg-brand text-white" : ""}`}>{t(`roadmap.${s.status}`)}</span>
                {s.conditional && s.status === "upcoming" && <span className="text-xs text-muted">{t("roadmap.ifNeeded")}</span>}
              </div>
              <div className="mt-0.5 text-xs text-muted">
                {s.finished_on && <span>{t("roadmap.finished")} {fmt(s.finished_on)}. </span>}
                {s.due_on && s.status !== "done" && <span className="font-semibold text-ink">{t("roadmap.due")}: {fmt(s.due_on)}. </span>}
                {s.estimated_on && !s.due_on && <span>{t("roadmap.estimated")}: {fmt(s.estimated_on)}. </span>}
                {s.detail}
                {s.norm_ref?.includes("TODO") && s.status !== "skipped" && s.kind === "document" && (
                  <span className="ms-1 text-warning">({t("roadmap.todoNorm")})</span>
                )}
              </div>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
