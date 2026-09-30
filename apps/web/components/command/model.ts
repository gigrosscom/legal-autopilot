// What the command centre shows, read from the team's files (lib/team.ts) and /v1/admin/metrics. No invented numbers:
// a value that is not in the data is null and the screen says «нет данных».

import {
  bullets, cell, colOf, isEmpty, number, plain, reportTitle, ruDate, section, sections, tableWith, taskState,
  type Bundle, type TaskState,
} from "@/lib/team";

export type Metrics = {
  generated_at: string;
  totals: Record<string, number>;
  today?: { users: number; cases: number; documents: number };
  payments?: { paid: number; paid_clients: number; paid_plans: number; paid_today: number;
    revenue: Record<string, string>; revenue_today: Record<string, string>; awaiting_confirmation: number };
  referral?: { users: number; referred_users: number; inviters: number; users_with_link: number;
    k_factor: number | null; sources: Record<string, number> };
  chat?: { day: string; gemini: number; free: number; anthropic: number; unavailable: number; anthropic_cost_usd: number };
  claude?: { today_usd: number; month_usd: number; daily_budget_usd: number; monthly_budget_usd: number;
    by_task: Record<string, { calls: number; cost_usd: number }> };
  weekly: { week: string; users: number; cases: number; documents: number; submitted: number }[];
};

export const F = {
  readme: "team/README.md", sessions: "team/sessions.md", decisions: "team/decisions.md",
  backlog: "team/backlog.md", plan: "team/plan-month-1.md",
};

export type Task = { id: string; text: string; role: string; due: string; status: string; state: TaskState };
export type Session = { name: string; url: string | null; branch: string; doing: string; status: string; waits: string;
  shipped: string[] };
export type Role = { name: string; owns: string; result: string; key: RegExp };
export type Decision = { date: string; text: string; source: string };
export type Pending = { from: string; text: string; kind: "task" | "session" | "report"; ref?: string };

export function backlog(b: Bundle | null): Task[] {
  const t = tableWith(b?.texts[F.backlog], /^Задача$/i);
  if (!t) return [];
  const [id, text, role, due, status] = [/^#|№/, /^Задача$/i, /^Роль|Кто|Владелец/i, /^Срок/i, /^Статус/i].map((r) => colOf(t, r));
  return t.rows.map((r) => ({
    id: plain(cell(r, id)), text: cell(r, text), role: plain(cell(r, role)), due: plain(cell(r, due)),
    status: plain(cell(r, status)), state: taskState(cell(r, status)),
  }));
}

export function sessionsOf(b: Bundle | null): Session[] {
  const md = b?.texts[F.sessions];
  const t = tableWith(md, /^Сессия$/i);
  if (!t) return [];
  const [name, branch, doing, status, waits] = [/^Сессия$/i, /^Ветка/i, /Чем занимается/i, /^Статус/i, /Ждёт|Ждет/i]
    .map((r) => colOf(t, r));
  // «## Что выложено сегодня из сессии «…»» sections belong to that session
  const shippedBy = sections(md).filter((s) => /выложено/i.test(s.heading));
  return t.rows.map((r) => {
    const raw = cell(r, name);
    const link = raw.match(/\[([^\]]+)\]\(([^)\s]+)\)/);
    const n = link ? link[1] : plain(raw);
    const shipped = shippedBy.filter((s) => s.heading.toLowerCase().includes(n.toLowerCase()))
      .flatMap((s) => bullets(s.body).map((x) => x.text));
    return { name: n, url: link ? link[2] : null, branch: cell(r, branch), doing: cell(r, doing), status: cell(r, status),
      waits: cell(r, waits), shipped };
  });
}

function roleKey(name: string): RegExp {
  const n = name.toLowerCase();
  if (n.includes("менеджер проекта")) return /менеджер проекта/i;
  if (n.includes("маркетолог")) return /маркетолог|маркетинг/i;
  if (n.includes("smm")) return /smm/i;
  if (n.includes("клиент")) return /клиент/i;
  if (n.includes("аккаунт")) return /аккаунт|продажи юристам/i;
  if (n.includes("финанс")) return /финанс/i;
  const first = n.split(/[\s—(,-]+/).find(Boolean) ?? n;
  return new RegExp(first.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "i");
}

export function rolesOf(b: Bundle | null): Role[] {
  const t = tableWith(b?.texts[F.readme], /^Роль$/i);
  if (!t) return [];
  const [name, owns, result] = [/^Роль$/i, /Отвечает/i, /результат/i].map((r) => colOf(t, r));
  return t.rows.map((r) => ({ name: plain(cell(r, name)), owns: cell(r, owns), result: cell(r, result),
    key: roleKey(plain(cell(r, name))) }));
}

export function decisionsOf(b: Bundle | null): Decision[] {
  const t = tableWith(b?.texts[F.decisions], /^Решение$/i);
  if (!t) return [];
  const [date, text, source] = [/^Дата/i, /^Решение$/i, /Источник|Кто/i].map((r) => colOf(t, r));
  return t.rows.map((r) => ({ date: plain(cell(r, date)), text: cell(r, text), source: plain(cell(r, source)) })).reverse();
}

export function latestReport(b: Bundle | null): { name: string; path: string; title: string; text: string } | null {
  const r = b?.reports[0];
  const text = r ? b?.texts[r.path] : null;
  return r && text ? { ...r, title: reportTitle(r.name), text } : null;
}

/** What waits for the owner: backlog tasks «ждёт владельца», sessions' «Ждёт от владельца», the latest report's
 * blockers and questions. */
export function pendingOf(b: Bundle | null): Pending[] {
  const out: Pending[] = [];
  for (const s of sessionsOf(b)) {
    if (!isEmpty(s.waits)) out.push({ from: s.name, text: s.waits, kind: "session" });
  }
  for (const t of backlog(b)) {
    if (t.state === "waiting") out.push({ from: `Задача №${t.id}${t.role ? ` · ${t.role}` : ""}`, text: t.text, kind: "task", ref: t.id });
  }
  const rep = latestReport(b);
  if (rep) {
    for (const s of sections(rep.text).filter((x) => /блокер|вопрос|ждёт решения|ждет решения|на решение|решения владельца/i.test(x.heading))) {
      for (const x of bullets(s.body)) out.push({ from: `Отчёт ${rep.title} · ${s.heading}`, text: x.text, kind: "report", ref: rep.path });
    }
  }
  return out;
}

/** The latest report's lines about one role (the «**Роль** — …» items of its sections). */
export function reportLines(b: Bundle | null, key: RegExp): string[] {
  const rep = latestReport(b);
  if (!rep) return [];
  const out: string[] = [];
  for (const x of bullets(rep.text)) {
    const label = x.text.match(/^\*\*([^*]+)\*\*/);
    if (label && key.test(label[1])) out.push([x.text, ...x.children.map((c) => `· ${c}`)].join("\n"));
  }
  return out;
}

export type Kpi = { name: string; target: number | null; how: string };

export function goalsOf(b: Bundle | null): { kpis: Kpi[]; days: number | null; start: Date | null } {
  const md = b?.texts[F.readme];
  const t = tableWith(md, /^Показатель$/i);
  const kpis: Kpi[] = [];
  let days: number | null = null;
  if (t) {
    const [name, target, how] = [/^Показатель$/i, /^Цель/i, /Как счита/i].map((r) => colOf(t, r));
    const d = t.headers[target]?.match(/(\d+)\s*дн/);
    days = d ? Number(d[1]) : null;
    for (const r of t.rows) kpis.push({ name: plain(cell(r, name)), target: number(cell(r, target)), how: cell(r, how) });
  }
  // the month starts with the owner's KPI decision
  const kpiDecision = [...decisionsOf(b)].reverse().find((x) => /KPI/.test(x.text));
  return { kpis, days, start: kpiDecision ? ruDate(kpiDecision.date) : null };
}

export function planSection(b: Bundle | null, re: RegExp) {
  return section(b?.texts[F.plan], re);
}

export const fmt = (n: number | null | undefined) => (n == null ? "—" : n.toLocaleString("ru-RU"));
export const usd = (n: number | null | undefined) => (n == null ? "—" : `$${n.toFixed(2)}`);
export function moneyText(r: Record<string, string> | undefined): string {
  const e = Object.entries(r ?? {});
  if (!e.length) return "0";
  return e.map(([c, v]) => `${Number(v).toLocaleString("ru-RU")} ${c === "KZT" ? "₸" : c}`).join(" · ");
}
