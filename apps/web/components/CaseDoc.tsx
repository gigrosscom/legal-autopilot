"use client";

import { useEffect, useRef, type ReactNode } from "react";
import { Icon, type IconName } from "@/components/ui";
import type { Roadmap, RoadmapStep } from "@/lib/api";
import { useLang, useT } from "@/lib/i18n";

/** A bottom sheet for one secondary action on the case screen (owner 02.10: each action opens its own sheet, so the
 *  main screen stays one step + milestones + a couple of buttons). Accessible: a labelled modal dialog, focus moves
 *  into it on open, Escape and the backdrop close it, the body scrolls on its own and keeps clear of the keyboard and
 *  the home indicator. Anchored to the bottom on phones, centred on wider screens — the same shape as «Ещё» and the
 *  payment window. */
export function Sheet({ title, icon, onClose, children }: {
  title: string; icon?: IconName; onClose: () => void; children: ReactNode;
}) {
  const t = useT();
  const panel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", esc);
    panel.current?.focus();
    return () => document.removeEventListener("keydown", esc);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center" role="dialog" aria-modal="true" aria-labelledby="sheet-title">
      <button type="button" aria-label={t("app.close")} onClick={onClose} className="absolute inset-0 bg-ink/40" />
      <div ref={panel} tabIndex={-1}
        className="relative flex max-h-[92dvh] w-full max-w-lg flex-col rounded-t-3xl bg-surface pb-[env(safe-area-inset-bottom)] shadow-[var(--shadow-raised)] outline-none sm:rounded-3xl">
        <div className="flex items-center gap-2 border-b border-line py-2 ps-4 pe-2">
          {icon && <Icon name={icon} className="text-brand" />}
          <h2 id="sheet-title" className="flex-1 truncate text-lg font-semibold">{title}</h2>
          <button type="button" onClick={onClose} aria-label={t("app.close")}
            className="flex h-11 w-11 items-center justify-center rounded-full hover:bg-sand"><Icon name="x" size={22} /></button>
        </div>
        <div className="space-y-3 overflow-y-auto overscroll-contain p-4">{children}</div>
      </div>
    </div>
  );
}

const DOT: Record<RoadmapStep["status"], string> = {
  done: "bg-brand-solid text-white border-brand",
  current: "bg-surface text-brand border-brand ring-4 ring-brand/15",
  upcoming: "bg-surface text-muted border-line",
  skipped: "bg-sand text-muted border-line",
};

/** The case milestones as a compact vertical lane (owner 02.10): «Документ составлен ✓ → Подписать → Отправить →
 *  Ждём ответ → иск в суд», so the person sees where the case is now. The steps and dates come from the case route
 *  (the roadmap), never made up here. */
export function DocMilestones({ roadmap }: { roadmap: Roadmap }) {
  const t = useT();
  const { lang } = useLang();
  const fmt = (iso: string | null) => (iso ? new Date(iso + "T00:00:00").toLocaleDateString(lang === "ar" ? "ar" : "ru-RU") : "");
  const steps = roadmap.steps;
  return (
    <section className="card space-y-3" aria-labelledby="milestones-title">
      <h2 id="milestones-title" className="font-semibold">{t("case.milestones")}</h2>
      <ol className="relative">
        {steps.map((s, i) => {
          const date = s.due_on && s.status !== "done" ? fmt(s.due_on) : s.finished_on && s.status === "done" ? fmt(s.finished_on) : "";
          return (
            <li key={s.key} className={`relative flex gap-3 pb-3 last:pb-0 ${s.status === "skipped" ? "opacity-50" : ""}`}>
              {i < steps.length - 1 && (
                <span aria-hidden className={`absolute start-[11px] top-6 h-[calc(100%-1rem)] w-0.5 ${s.status === "done" ? "bg-brand" : "bg-line"}`} />
              )}
              <span className={`z-10 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border-2 text-[11px] font-semibold ${DOT[s.status]}`}>
                {s.status === "done" ? <Icon name="check" size={13} /> : i + 1}
              </span>
              <div className="min-w-0 flex-1 pt-0.5">
                <p className={`text-[15px] leading-snug ${s.status === "current" ? "font-semibold text-ink" : s.status === "done" ? "text-ink" : "text-muted"} ${s.status === "skipped" ? "line-through" : ""}`}>
                  {s.title}
                  {s.status === "current" && <span className="ms-2 align-middle text-xs font-medium text-brand">{t("roadmap.current")}</span>}
                </p>
                {date && (
                  <p className="text-xs text-muted">
                    {s.status === "done" ? t("roadmap.finished") : t("roadmap.due")} {date}
                  </p>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
