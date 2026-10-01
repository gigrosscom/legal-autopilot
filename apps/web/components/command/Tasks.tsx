"use client";

import { useMemo, useState } from "react";
import { MdInline } from "@/components/Markdown";
import { isEmpty, plain, type TaskState } from "@/lib/team";
import { backlog, F, type Task } from "./model";
import { Chip, Loading, PageTitle, TeamUnavailable, useCentre } from "./ui";

// owner 01.10: новое → передано → в работе → ждёт владельца → готово
const COLUMNS: { key: TaskState; label: string }[] = [
  { key: "new", label: "Новые" }, { key: "passed", label: "Передано" }, { key: "doing", label: "В работе" },
  { key: "waiting", label: "Ждёт владельца" }, { key: "done", label: "Готово" },
];

/** «01.10», «01.10.2026», «2026-10-01» → is it past? (a task still open after its date is shown in red) */
function overdue(due: string, state: TaskState): boolean {
  if (state === "done") return false;
  const m = due.match(/(\d{1,2})\.(\d{1,2})(?:\.(\d{4}))?/) ?? null;
  const iso = due.match(/(\d{4})-(\d{2})-(\d{2})/);
  const d = iso ? new Date(+iso[1], +iso[2] - 1, +iso[3]) : m ? new Date(m[3] ? +m[3] : new Date().getFullYear(), +m[2] - 1, +m[1]) : null;
  if (!d) return false;
  const today = new Date(); today.setHours(0, 0, 0, 0);
  return d < today;
}

function TaskCard({ t }: { t: Task }) {
  return (
    <li className="space-y-2 rounded-2xl bg-surface p-3 shadow-[0_1px_2px_rgb(0_0_0/0.06)] ring-1 ring-ink/[0.05]">
      <p className="text-[16px] leading-snug"><span className="me-1.5 text-muted tabular-nums">№{t.id}</span><MdInline text={t.text} /></p>
      <div className="flex flex-wrap gap-1.5">
        {!isEmpty(t.role) && <Chip tone="blue">{t.role}</Chip>}
        {!isEmpty(t.due) && (overdue(t.due, t.state)
          ? <span className="inline-flex items-center rounded-full bg-danger-strong px-2.5 py-0.5 text-[13px] font-semibold text-white">просрочено · {t.due}</span>
          : <Chip>срок {t.due}</Chip>)}
        {t.state === "other" || t.status.toLowerCase() !== COLUMNS.find((c) => c.key === t.state)?.label.toLowerCase()
          ? <Chip tone={t.state === "waiting" ? "warn" : t.state === "done" ? "done" : "neutral"}>{t.status}</Chip> : null}
      </div>
    </li>
  );
}

/** team/backlog.md as a board: by status, filter by role, search. Read-only: the project manager keeps the file. */
export function Tasks() {
  const c = useCentre();
  const all = useMemo(() => backlog(c.bundle), [c.bundle]);
  const [role, setRole] = useState("");
  const [q, setQ] = useState("");
  const [col, setCol] = useState<TaskState>("waiting");  // the phone opens on what waits for the owner
  const roles = useMemo(() => [...new Set(all.flatMap((t) => t.role.split(/,\s*/)).map((r) => r.trim()).filter((r) => r && r !== "—"))].sort(), [all]);
  if (c.teamError) return <div className="space-y-6"><PageTitle>Задачи</PageTitle><TeamUnavailable /></div>;
  if (!c.bundle) return <div className="space-y-6"><PageTitle>Задачи</PageTitle><Loading /></div>;

  const needle = q.trim().toLowerCase();
  const shown = all.filter((t) => (!role || t.role.split(/,\s*/).map((r) => r.trim()).includes(role))
    && (!needle || plain(`${t.id} ${t.text} ${t.role} ${t.status}`).toLowerCase().includes(needle)));
  const by = (k: TaskState) => shown.filter((t) => t.state === k || (k === "new" && t.state === "other"));

  return (
    <div className="space-y-5">
      <PageTitle sub={<>Бэклог команды (backlog.md): {all.length} задач · <button type="button" className="text-brand" onClick={() => c.openFile(F.backlog)}>открыть файл</button></>}>
        Задачи
      </PageTitle>
      <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Поиск по задачам"
        className="min-h-12 w-full rounded-full bg-sand px-5 text-[17px] outline-none placeholder:text-muted focus:ring-2 focus:ring-accent" />
      <div className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1 [scrollbar-width:none]">
        {["", ...roles].map((r) => (
          <button key={r || "all"} onClick={() => setRole(r)}
            className={`min-h-10 shrink-0 rounded-full px-4 text-[15px] font-semibold ${role === r ? "bg-ink text-surface" : "bg-sand hover:bg-sand-deep"}`}>{r || "Все роли"}</button>
        ))}
      </div>

      {/* phone: one status at a time */}
      <div className="lg:hidden">
        <div className="grid grid-cols-5 gap-1 rounded-full bg-sand p-1">
          {COLUMNS.map((k) => (
            <button key={k.key} onClick={() => setCol(k.key)} aria-pressed={col === k.key}
              className={`min-h-10 rounded-full px-1 text-[13px] font-semibold leading-tight ${col === k.key ? "bg-surface shadow-sm" : "text-muted"}`}>
              {k.label.replace("Ждёт владельца", "Ждёт вас")} <span className="tabular-nums">{by(k.key).length}</span>
            </button>
          ))}
        </div>
        <ul className="mt-3 space-y-2">
          {by(col).map((t) => <TaskCard key={`${t.id}-${t.text.slice(0, 12)}`} t={t} />)}
          {by(col).length === 0 && <li className="text-muted">Нет задач.</li>}
        </ul>
      </div>

      {/* computer: the board */}
      <div className="hidden gap-3 lg:grid lg:grid-cols-5">
        {COLUMNS.map((k) => (
          <section key={k.key} className="rounded-2xl bg-sand p-3">
            <h2 className="flex items-center justify-between px-1 pb-2 text-[16px] font-semibold">{k.label}<span className="text-muted tabular-nums">{by(k.key).length}</span></h2>
            <ul className="space-y-2">{by(k.key).map((t) => <TaskCard key={`${t.id}-${t.text.slice(0, 12)}`} t={t} />)}</ul>
          </section>
        ))}
      </div>
    </div>
  );
}
