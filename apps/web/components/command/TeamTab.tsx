"use client";

import { useEffect, useState, type ReactNode } from "react";
import { MdInline } from "@/components/Markdown";
import { Icon } from "@/components/ui";
import { adminApi } from "@/lib/api";
import { csv, isEmpty, plain } from "@/lib/team";
import { backlog, F, fmt, moneyText, reportLines, rolesOf, sessionsOf, usd, type Metrics, type Role, type Task } from "./model";
import { Chip, H2, Loading, NoData, PageTitle, TeamUnavailable, useCentre } from "./ui";

type Figure = [string, ReactNode];

/** Row counts of the team's CSV bases (leads), read once for the account manager's figures. */
function useCsvRows(paths: string[]): Record<string, number | null> {
  const { token, bundle } = useCentre();
  const [out, setOut] = useState<Record<string, number | null>>({});
  const key = paths.join(",");
  useEffect(() => {
    const known = new Set(bundle?.files.map((f) => f.path));
    for (const p of key.split(",").filter(Boolean)) {
      if (!known.has(p)) { setOut((o) => ({ ...o, [p]: null })); continue; }
      adminApi<{ text: string }>(`/v1/admin/team/file?path=${encodeURIComponent(p)}`, token)
        .then((r) => setOut((o) => ({ ...o, [p]: Math.max(0, csv(r.text).length - 1) })))
        .catch(() => setOut((o) => ({ ...o, [p]: null })));
    }
  }, [key, token, bundle]);
  return out;
}

const count = (files: { path: string }[] | undefined, re: RegExp) => (files ?? []).filter((f) => re.test(f.path)).length;

/** Each role's own figures, only from real data (metrics, the team's files). */
function figures(role: Role, m: Metrics | null, files: { path: string }[] | undefined, tasks: Task[], rows: Record<string, number | null>,
  reports: number): Figure[] {
  const n = role.name.toLowerCase();
  const nd = <NoData />;
  const val = (v: number | null | undefined) => (v == null ? nd : fmt(v));
  if (n.includes("менеджер проекта")) {
    const done = tasks.filter((t) => t.state === "done").length;
    return [["Отчётов владельцу", fmt(reports)], ["Задач команды закрыто", `${fmt(done)} из ${fmt(tasks.length)}`]];
  }
  if (n.includes("маркетолог")) {
    return [["Пришли по приглашению", val(m?.referral?.referred_users)],
      ["K-фактор", m?.referral?.k_factor == null ? nd : m.referral.k_factor.toLocaleString("ru-RU")]];
  }
  if (n.includes("smm")) {
    return [["Пакетов контента готово", fmt(count(files, /^team\/content\/\d{4}-\d{2}-\d{2}\.md$/))], ["Опубликовано постов", nd]];
  }
  if (n.includes("клиент")) {
    const c = m?.chat;
    return [["Ответов в чате сегодня", c ? fmt(c.gemini + c.free + c.anthropic) : nd],
      ["Не ответили (нагрузка) сегодня", c ? fmt(c.unavailable) : nd]];
  }
  if (n.includes("аккаунт")) {
    return [["Юристов в базе", val(rows["team/leads/lawyers.csv"])], ["Партнёров в базе", val(rows["team/leads/partners.csv"])],
      ["Пакетов писем", fmt(count(files, /^team\/outreach\/.+\.md$/))], ["Заявок юристов на сайте", val(m?.totals.lawyer_applications)],
      ["Писем отправлено", nd]];
  }
  if (n.includes("финанс")) {
    return [["Выручка", m?.payments ? moneyText(m.payments.revenue) : nd],
      ["Claude за месяц", m?.claude ? `${usd(m.claude.month_usd)} из ${usd(m.claude.monthly_budget_usd)}` : nd]];
  }
  return [];
}

function Block({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div>
      <p className="text-[13px] font-semibold tracking-wide text-muted uppercase">{title}</p>
      <div className="mt-1 text-[16px]">{children}</div>
    </div>
  );
}

function TaskList({ tasks }: { tasks: Task[] }) {
  const open = tasks.filter((t) => t.state !== "done");
  const done = tasks.length - open.length;
  if (!tasks.length) return <NoData>задач в бэклоге нет</NoData>;
  return (
    <>
      <ul className="space-y-1.5">
        {open.map((t) => (
          <li key={t.id} className="flex gap-2">
            <span className="shrink-0 text-muted tabular-nums">№{t.id}</span>
            <span className="min-w-0">
              <span className="line-clamp-3"><MdInline text={t.text} /></span>
              <span className="mt-0.5 flex flex-wrap gap-1.5">
                <Chip tone={t.state === "waiting" ? "warn" : t.state === "doing" ? "blue" : "neutral"}>{t.status}</Chip>
                {!isEmpty(t.due) && <Chip>срок {t.due}</Chip>}
              </span>
            </span>
          </li>
        ))}
      </ul>
      {done > 0 && <p className="mt-2 text-[15px] text-muted">Готово: {done}</p>}
    </>
  );
}

function MemberCard({ title, subtitle, avatar, children }: { title: ReactNode; subtitle?: ReactNode; avatar: ReactNode; children: ReactNode }) {
  return (
    <article className="space-y-4 rounded-2xl bg-sand p-4">
      <header className="flex items-start gap-3">
        <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-action text-[17px] font-semibold text-white">{avatar}</span>
        <div className="min-w-0">
          <h3 className="text-[18px] leading-snug font-semibold">{title}</h3>
          {subtitle && <p className="text-[15px] text-muted">{subtitle}</p>}
        </div>
      </header>
      {children}
    </article>
  );
}

export function TeamTab() {
  const c = useCentre();
  const { bundle, metrics: m } = c;
  const rows = useCsvRows(["team/leads/lawyers.csv", "team/leads/partners.csv"]);
  const [filter, setFilter] = useState<"all" | "roles" | "sessions">("all");
  if (c.teamError) return <div className="space-y-6"><PageTitle>Команда</PageTitle><TeamUnavailable /></div>;
  if (!bundle) return <div className="space-y-6"><PageTitle>Команда</PageTitle><Loading /></div>;
  const roles = rolesOf(bundle);
  const sessions = sessionsOf(bundle);
  const tasks = backlog(bundle);

  return (
    <div className="space-y-6">
      <PageTitle sub="Кто чем занят, что сделано, задачи и что ждут от вас. Источник: README.md, sessions.md, backlog.md и последний отчёт.">
        Команда
      </PageTitle>
      <div role="tablist" className="flex gap-2">
        {([["all", "Все"], ["roles", `ИИ-роли · ${roles.length}`], ["sessions", `Сессии Claude · ${sessions.length}`]] as const).map(([k, label]) => (
          <button key={k} role="tab" aria-selected={filter === k} onClick={() => setFilter(k)}
            className={`min-h-10 rounded-full px-4 text-[15px] font-semibold ${filter === k ? "bg-ink text-white" : "bg-sand text-ink hover:bg-sand-deep"}`}>{label}</button>
        ))}
      </div>

      {filter !== "sessions" && (
        <section className="space-y-3">
          <H2 count={roles.length}>ИИ-роли</H2>
          {roles.length === 0 && <p className="text-muted">В team/README.md нет таблицы ролей.</p>}
          <div className="grid gap-3 xl:grid-cols-2">
            {roles.map((r) => {
              const mine = tasks.filter((t) => r.key.test(t.role));
              const lines = reportLines(bundle, r.key);
              const waits = mine.filter((t) => t.state === "waiting");
              const figs = figures(r, m, bundle.files, tasks, rows, bundle.reports.length);
              return (
                <MemberCard key={r.name} title={r.name} subtitle={<MdInline text={r.owns} />} avatar={plain(r.name).slice(0, 1)}>
                  <Block title="Показатели">
                    {figs.length === 0 ? <NoData /> : (
                      <dl className="grid grid-cols-2 gap-2">
                        {figs.map(([label, v]) => (
                          <div key={label} className="rounded-xl bg-surface px-3 py-2">
                            <dt className="text-[13px] text-muted">{label}</dt>
                            <dd className="text-[18px] font-semibold tabular-nums">{v}</dd>
                          </div>
                        ))}
                      </dl>
                    )}
                  </Block>
                  <Block title="Сделано (последний отчёт)">
                    {lines.length === 0 ? <NoData>в последнем отчёте нет строки этой роли</NoData> : (
                      <ul className="space-y-1.5">{lines.map((l, i) => <li key={i} className="whitespace-pre-line"><MdInline text={l} base="team/reports/" onFile={c.openFile} /></li>)}</ul>
                    )}
                  </Block>
                  <Block title="Задачи"><TaskList tasks={mine} /></Block>
                  <Block title="Ждёт от владельца">
                    {waits.length === 0 ? <NoData>ничего</NoData> : (
                      <ul className="list-disc space-y-1 ps-5">{waits.map((t) => <li key={t.id}>№{t.id}: <MdInline text={t.text} /></li>)}</ul>
                    )}
                  </Block>
                  <Block title="Главный результат"><MdInline text={r.result} /></Block>
                </MemberCard>
              );
            })}
          </div>
        </section>
      )}

      {filter !== "roles" && (
        <section className="space-y-3">
          <H2 count={sessions.length}>Сессии Claude</H2>
          {sessions.length === 0 && <p className="text-muted">В team/sessions.md нет таблицы сессий.</p>}
          <div className="grid gap-3 xl:grid-cols-2">
            {sessions.map((s) => {
              const mine = tasks.filter((t) => {
                const text = `${t.text} ${t.role}`.toLowerCase();
                const branch = plain(s.branch).split(/\s|→|\(/)[0].toLowerCase();
                return (branch.length > 4 && text.includes(branch)) || text.includes(s.name.toLowerCase());
              });
              return (
                <MemberCard key={s.name} avatar={<Icon name="sparkle" size={20} />}
                  title={s.url ? <a href={s.url} target="_blank" rel="noopener noreferrer" className="hover:underline">{s.name}</a> : s.name}
                  subtitle={<span className="break-all"><MdInline text={s.branch} /></span>}>
                  <Block title="Чем занимается"><MdInline text={s.doing} /></Block>
                  <Block title="Статус сейчас"><MdInline text={s.status} /></Block>
                  {s.shipped.length > 0 && (
                    <Block title="Сделано">
                      <ul className="list-disc space-y-1 ps-5">{s.shipped.map((x, i) => <li key={i}><MdInline text={x} /></li>)}</ul>
                    </Block>
                  )}
                  {mine.length > 0 && <Block title="Задачи в бэклоге"><TaskList tasks={mine} /></Block>}
                  <Block title="Ждёт от владельца">
                    {isEmpty(s.waits) ? <NoData>ничего</NoData> : <span className="font-medium"><MdInline text={s.waits} /></span>}
                  </Block>
                  {s.url && (
                    <a href={s.url} target="_blank" rel="noopener noreferrer"
                      className="inline-flex min-h-10 items-center gap-2 rounded-full bg-surface px-4 text-[15px] font-semibold ring-1 ring-line hover:bg-sand-deep">
                      Открыть сессию<Icon name="external" size={16} />
                    </a>
                  )}
                </MemberCard>
              );
            })}
          </div>
          <button type="button" onClick={() => c.openFile(F.sessions)} className="text-[16px] font-semibold text-brand">Открыть sessions.md целиком</button>
        </section>
      )}
    </div>
  );
}
