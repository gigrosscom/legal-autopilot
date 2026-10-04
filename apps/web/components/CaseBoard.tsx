"use client";

import Link from "next/link";
import { Icon } from "@/components/ui";
import { LevelBadge, type Level } from "@/components/LevelBadge";
import { useT } from "@/lib/i18n";

export const COLUMNS = ["intake", "qualified", "action_ready", "submitted", "escalated", "handed_to_lawyer",
  "resolved"] as const;

export type BoardCard = {
  id: string;
  title: string;
  stage: string;
  level: string;
  date?: string;
  meta?: string;
  attention?: string | null;
  due?: { text: string; late: boolean } | null;
  tasks?: { label: string; done: boolean }[];
  href: string;
};

/**
 * Kanban: every case sits in exactly one lifecycle column and never disappears (resolved stays visible).
 * Desktop: columns side by side inside their own scroll area; phones: columns stacked, empty ones collapsed.
 */
export function CaseBoard({ cards, onlyNonEmptyOnMobile = true, onOpen }: {
  cards: BoardCard[]; onlyNonEmptyOnMobile?: boolean; onOpen?: (id: string) => void;
}) {
  const t = useT();
  const by = Object.fromEntries(COLUMNS.map((c) => [c, cards.filter((x) => x.stage === c)]));
  return (
    <div className="-mx-4 overflow-x-auto px-4 pb-2 lg:mx-0 lg:px-0">
      <ol className="grid grid-cols-[minmax(0,1fr)] gap-3 lg:min-w-[1100px] lg:grid-cols-7">
        {COLUMNS.map((col) => {
          const items = by[col];
          const hide = onlyNonEmptyOnMobile && items.length === 0 ? "hidden lg:flex" : "flex";
          return (
            <li key={col} className={`${hide} min-w-0 flex-col gap-2 rounded-2xl bg-sand-deep/60 p-2`}>
              <h3 className="flex items-center justify-between px-2 pt-1 text-sm font-semibold">
                <span>{t(`board.${col}`)}</span>
                <span className="rounded-full bg-surface px-2 text-xs text-muted tabular-nums">{items.length}</span>
              </h3>
              {items.length === 0 && <p className="px-2 pb-2 text-xs text-muted">{t("board.empty")}</p>}
              {items.map((c) => {
                const cls = "card block w-full space-y-2 p-3 text-start transition-shadow hover:shadow-[var(--shadow-raised)]";
                const body = (<>
                  <div className="flex flex-wrap items-center gap-1.5"><LevelBadge level={c.level as Level} /></div>
                  <p className="text-sm font-semibold leading-snug">{c.title}</p>
                  {c.meta && <p className="text-xs text-muted">{c.meta}</p>}
                  {c.due && (
                    <p className={`flex items-center gap-1 text-xs font-medium ${c.due.late ? "text-danger" : "text-ink-soft"}`}>
                      <Icon name="clock" size={14} />{c.due.text}
                    </p>
                  )}
                  {c.attention && (
                    <p className="flex items-center gap-1 text-xs font-medium text-warning">
                      <Icon name="alert" size={14} />{c.attention}
                    </p>
                  )}
                  {c.tasks && c.tasks.length > 0 && (
                    <ul className="space-y-1 border-t border-line pt-2">
                      {c.tasks.map((task, i) => (
                        <li key={i} className="flex items-center gap-1.5 text-xs text-muted">
                          <Icon name={task.done ? "checkCircle" : "clock"} size={14}
                            className={task.done ? "text-brand" : ""} />
                          <span className="truncate">{task.label}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                  {c.date && <p className="text-xs text-muted tabular-nums">{c.date}</p>}
                </>);
                return onOpen
                  ? <button key={c.id} type="button" className={cls} onClick={() => onOpen(c.id)}>{body}</button>
                  : <Link key={c.id} href={c.href} className={cls}>{body}</Link>;
              })}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
