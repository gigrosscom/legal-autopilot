"use client";

import { createContext, useContext, type ReactNode } from "react";
import { Icon, type IconName } from "@/components/ui";
import type { Bundle } from "@/lib/team";
import type { Metrics } from "./model";

export type TabKey = "home" | "goals" | "team" | "tasks" | "decisions" | "reports" | "ops";

export type Centre = {
  token: string;
  metrics: Metrics | null;
  metricsError: string | null;
  bundle: Bundle | null;
  /** null: loaded; "unavailable": the team's files could not be read; other text: an error */
  teamError: string | null;
  go: (tab: TabKey) => void;
  openFile: (path: string) => void;
  reload: () => void;
};

export const CentreContext = createContext<Centre | null>(null);
export function useCentre(): Centre {
  const c = useContext(CentreContext);
  if (!c) throw new Error("CentreContext missing");
  return c;
}

export function PageTitle({ children, sub, actions }: { children: ReactNode; sub?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        <h1 className="text-[28px] leading-tight font-semibold">{children}</h1>
        {sub && <p className="mt-1 text-[15px] text-muted">{sub}</p>}
      </div>
      {actions}
    </div>
  );
}

export function H2({ children, count, action }: { children: ReactNode; count?: number; action?: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <h2 className="text-xl font-semibold">
        {children}
        {count != null && <span className="ms-2 inline-flex min-w-7 items-center justify-center rounded-full bg-sand px-2 text-[15px] font-semibold text-muted">{count}</span>}
      </h2>
      {action}
    </div>
  );
}

export function Card({ children, className = "", as: Tag = "div" }: { children: ReactNode; className?: string; as?: "div" | "article" | "li" }) {
  return <Tag className={`rounded-2xl bg-sand p-4 ${className}`}>{children}</Tag>;
}

export function Stat({ label, value, note, tone }: { label: string; value: ReactNode; note?: ReactNode; tone?: "warn" }) {
  return (
    <div className="rounded-2xl bg-sand p-4">
      <dt className="text-[15px] text-muted">{label}</dt>
      <dd className={`mt-1 text-[26px] leading-tight font-semibold tabular-nums ${tone === "warn" ? "text-warning" : ""}`}>{value}</dd>
      {note && <dd className="mt-1 text-sm text-muted">{note}</dd>}
    </div>
  );
}

export function Progress({ value, max }: { value: number; max: number }) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  return (
    <div className="h-2.5 w-full overflow-hidden rounded-full bg-sand-deep" role="progressbar" aria-valuemin={0} aria-valuemax={max} aria-valuenow={value}>
      <div className="h-full rounded-full bg-action" style={{ width: `${Math.max(pct, value > 0 ? 1.5 : 0)}%` }} />
    </div>
  );
}

export function NoData({ children = "нет данных" }: { children?: ReactNode }) {
  return <span className="text-muted">{children}</span>;
}

export function Chip({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "blue" | "warn" | "done" }) {
  const cls = tone === "blue" ? "bg-brand-50 text-brand-dark" : tone === "warn" ? "bg-warning-50 text-warning"
    : tone === "done" ? "bg-[#e8f5ee] text-success" : "bg-surface text-muted ring-1 ring-line";
  return <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-[13px] font-medium ${cls}`}>{children}</span>;
}

/** The team's files could not be read (GitHub unreachable, no token for a private repository, TEAM_DIR wrong). */
export function TeamUnavailable() {
  const { teamError, reload } = useCentre();
  return (
    <div className="rounded-2xl bg-warning-50 p-4 text-[16px]">
      <p className="font-semibold">Файлы команды сейчас недоступны</p>
      <p className="mt-1 text-muted">
        {teamError === "unavailable"
          ? "Сервер не смог прочитать папку team/ из ветки claude/ai-team. Если репозиторий закрытый — добавьте TEAM_GITHUB_TOKEN в настройки сервера (docs/command-center.md). Цифры из метрик и оплаты работают."
          : teamError}
      </p>
      <button type="button" onClick={reload} className="mt-3 min-h-10 rounded-full bg-surface px-4 text-[15px] font-semibold ring-1 ring-line">Повторить</button>
    </div>
  );
}

export function Loading() {
  return (
    <p className="flex items-center gap-2 text-muted"><Icon name="spinner" size={18} className="animate-spin" />Загружаем…</p>
  );
}

export function RowLink({ icon, title, sub, onClick, href }: { icon?: IconName; title: ReactNode; sub?: ReactNode; onClick?: () => void; href?: string }) {
  const inner = (
    <>
      {icon && <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-surface text-brand"><Icon name={icon} size={20} /></span>}
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[17px] font-medium">{title}</span>
        {sub && <span className="block truncate text-[15px] text-muted">{sub}</span>}
      </span>
      <Icon name={href ? "external" : "arrowRight"} size={18} className="shrink-0 text-muted" />
    </>
  );
  const cls = "flex min-h-14 w-full items-center gap-3 rounded-2xl bg-sand px-4 py-3 text-start hover:bg-sand-deep";
  return href
    ? <a href={href} className={cls}>{inner}</a>
    : <button type="button" onClick={onClick} className={cls}>{inner}</button>;
}
