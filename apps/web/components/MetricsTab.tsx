"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui";
import { adminApi, downloadFile, errorText } from "@/lib/api";
import { useT } from "@/lib/i18n";

type Metrics = {
  generated_at: string;
  totals: Record<string, number>;
  funnel: { step: string; cases: number }[];
  outcomes: Record<string, number>;
  money: { at_stake: Record<string, string>; recovered: Record<string, string> };
  median_days_to_resolution: number | null;
  countries: Record<string, number>;
  top_scenarios: [string, number][];
  weekly: { week: string; users: number; cases: number; documents: number; submitted: number }[];
  claude?: { today_usd: number; month_usd: number; daily_budget_usd: number; monthly_budget_usd: number;
    by_task: Record<string, { calls: number; cost_usd: number }> };
};
type Series = "cases" | "users" | "documents" | "submitted";

const fmt = (n: number | string) => Number(n).toLocaleString("ru-RU");
const pct = (a: number, b: number) => (b ? `${Math.round((a / b) * 100)}%` : "—");

/** Traction for investors: counted from real cases only. KPI tiles, funnel, weekly growth, CSV export. */
export function MetricsTab({ token }: { token: string }) {
  const t = useT();
  const [m, setM] = useState<Metrics | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [series, setSeries] = useState<Series>("cases");
  useEffect(() => { adminApi<Metrics>("/v1/admin/metrics?weeks=12", token).then(setM).catch((e) => setErr(errorText(e))); }, [token]);
  if (err) return <p role="alert" className="text-sm text-danger">{err}</p>;
  if (!m) return <p className="text-muted">{t("common.loading")}</p>;

  const money = (r: Record<string, string>) => Object.entries(r).map(([c, v]) => `${fmt(v)} ${c}`).join(" · ") || "0";
  const positive = (m.outcomes.won ?? 0) + (m.outcomes.partial ?? 0) + (m.outcomes.settled ?? 0);
  const tiles: [string, string][] = [
    [t("metrics.users"), fmt(m.totals.users)],
    [t("metrics.cases"), fmt(m.totals.cases)],
    [t("metrics.documents"), fmt(m.totals.documents)],
    [t("metrics.submitted"), fmt(m.totals.submitted)],
    [t("metrics.positive"), fmt(positive)],
    [t("metrics.recovered"), money(m.money.recovered)],
    [t("metrics.atStake"), money(m.money.at_stake)],
    [t("metrics.medianDays"), m.median_days_to_resolution == null ? "—" : String(m.median_days_to_resolution)],
  ];
  const top = m.funnel[0]?.cases || 0;
  const max = Math.max(1, ...m.weekly.map((w) => w[series]));

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted">{t("metrics.lead")} · {new Date(m.generated_at).toLocaleString("ru-RU")}</p>
        <Button variant="secondary" icon="download"
          onClick={() => downloadFile("/v1/admin/metrics.csv?weeks=12", "konsilier-metrics.csv", { "X-Admin-Token": token })}>CSV</Button>
      </div>

      <dl className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {tiles.map(([label, value]) => (
          <div key={label} className="card space-y-1 p-4">
            <dt className="text-xs text-muted">{label}</dt>
            <dd className="text-2xl font-semibold tabular-nums">{value}</dd>
          </div>
        ))}
      </dl>

      <section className="card space-y-3" aria-labelledby="funnel-h">
        <h2 id="funnel-h" className="font-semibold">{t("metrics.funnel")}</h2>
        <ol className="space-y-2">
          {m.funnel.map((f, i) => (
            <li key={f.step} className="grid grid-cols-[minmax(0,11rem)_1fr_auto] items-center gap-3 text-sm"
              title={`${t(`metrics.step.${f.step}`)}: ${f.cases}`}>
              <span className="truncate">{t(`metrics.step.${f.step}`)}</span>
              <span className="h-5 rounded-e-[4px] bg-brand" style={{ width: `${top ? Math.max(1, (f.cases / top) * 100) : 0}%` }} />
              <span className="tabular-nums text-muted">
                {fmt(f.cases)}{i > 0 && <span className="ms-2 text-xs">{pct(f.cases, m.funnel[i - 1].cases)}</span>}
              </span>
            </li>
          ))}
        </ol>
      </section>

      <section className="card space-y-3" aria-labelledby="weekly-h">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 id="weekly-h" className="font-semibold">{t(`metrics.weekly.${series}`)}</h2>
          <div className="flex flex-wrap gap-1" role="tablist">
            {(["cases", "users", "documents", "submitted"] as Series[]).map((s) => (
              <button key={s} role="tab" aria-selected={series === s} onClick={() => setSeries(s)}
                className={`min-h-9 rounded-lg px-2.5 text-xs font-medium ${series === s ? "bg-ink text-white" : "bg-sand"}`}>
                {t(`metrics.${s}`)}
              </button>
            ))}
          </div>
        </div>
        <div className="flex h-40 items-end gap-1 border-b border-line" aria-hidden>
          {m.weekly.map((w) => (
            <div key={w.week} className="group relative flex h-full flex-1 items-end" title={`${w.week}: ${w[series]}`}>
              <div className="w-full rounded-t-[4px] bg-brand group-hover:bg-brand-dark" style={{ height: `${(w[series] / max) * 100}%`, minHeight: w[series] ? 2 : 0 }} />
            </div>
          ))}
        </div>
        <div className="flex justify-between text-xs text-muted"><span>{m.weekly[0]?.week}</span><span>{m.weekly.at(-1)?.week}</span></div>
        <details className="text-sm">
          <summary className="cursor-pointer text-muted">{t("metrics.table")}</summary>
          <div className="overflow-x-auto">
            <table className="mt-2 w-full text-end tabular-nums">
              <thead><tr className="text-xs text-muted"><th className="text-start">{t("metrics.week")}</th><th>{t("metrics.users")}</th><th>{t("metrics.cases")}</th><th>{t("metrics.documents")}</th><th>{t("metrics.submitted")}</th></tr></thead>
              <tbody>{m.weekly.map((w) => (
                <tr key={w.week} className="border-t border-line"><td className="py-1 text-start">{w.week}</td><td>{w.users}</td><td>{w.cases}</td><td>{w.documents}</td><td>{w.submitted}</td></tr>
              ))}</tbody>
            </table>
          </div>
        </details>
      </section>

      {m.claude && <ClaudeSpend c={m.claude} />}

      <div className="grid gap-4 md:grid-cols-2">
        <section className="card space-y-2 text-sm">
          <h2 className="font-semibold">{t("metrics.topScenarios")}</h2>
          <ul className="space-y-1">{m.top_scenarios.length ? m.top_scenarios.map(([id, n]) => (
            <li key={id} className="flex justify-between gap-2"><span className="truncate font-mono text-xs">{id}</span><span className="tabular-nums">{n}</span></li>
          )) : <li className="text-muted">—</li>}</ul>
        </section>
        <section className="card space-y-2 text-sm">
          <h2 className="font-semibold">{t("metrics.more")}</h2>
          <ul className="space-y-1">
            <li className="flex justify-between"><span>{t("metrics.repeat")}</span><span className="tabular-nums">{m.totals.repeat_users}</span></li>
            <li className="flex justify-between"><span>{t("metrics.lawyer")}</span><span className="tabular-nums">{m.totals.handed_to_lawyer}</span></li>
            <li className="flex justify-between"><span>{t("metrics.lawyerApps")}</span><span className="tabular-nums">{m.totals.lawyer_applications}</span></li>
            <li className="flex justify-between"><span>{t("metrics.waitlist")}</span><span className="tabular-nums">{m.totals.waitlist}</span></li>
            <li className="flex justify-between"><span>{t("metrics.countries")}</span><span>{Object.entries(m.countries).map(([c, n]) => `${c} ${n}`).join(" · ")}</span></li>
          </ul>
        </section>
      </div>
    </div>
  );
}

/** The paid model's spend today and this month against the budgets set on the server. */
function ClaudeSpend({ c }: { c: NonNullable<Metrics["claude"]> }) {
  const t = useT();
  const usd = (n: number) => `$${n.toFixed(2)}`;
  const bar = (spent: number, budget: number) => {
    const share = budget ? Math.min(1, spent / budget) : 0;
    return (
      <div className="h-2 rounded-full bg-sand" aria-hidden>
        <div className={`h-2 rounded-full ${share >= 1 ? "bg-danger" : share >= 0.8 ? "bg-warning" : "bg-brand"}`}
          style={{ width: `${Math.max(share * 100, spent ? 2 : 0)}%` }} />
      </div>
    );
  };
  const tasks = Object.entries(c.by_task).sort((a, b) => b[1].cost_usd - a[1].cost_usd);
  return (
    <section className="card space-y-3 text-sm" aria-labelledby="claude-h">
      <div className="space-y-1">
        <h2 id="claude-h" className="font-semibold">{t("metrics.claude.title")}</h2>
        <p className="text-xs text-muted">{t("metrics.claude.lead")}</p>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <div className="space-y-1">
          <p className="flex justify-between"><span>{t("metrics.claude.today")}</span><span className="tabular-nums">{usd(c.today_usd)} / {usd(c.daily_budget_usd)}</span></p>
          {bar(c.today_usd, c.daily_budget_usd)}
        </div>
        <div className="space-y-1">
          <p className="flex justify-between"><span>{t("metrics.claude.month")}</span><span className="tabular-nums">{usd(c.month_usd)} / {usd(c.monthly_budget_usd)}</span></p>
          {bar(c.month_usd, c.monthly_budget_usd)}
        </div>
      </div>
      {tasks.length > 0 && (
        <ul className="space-y-1">{tasks.map(([task, v]) => (
          <li key={task} className="flex justify-between gap-2"><span className="truncate font-mono text-xs">{task}</span>
            <span className="tabular-nums text-muted">{v.calls} · {usd(v.cost_usd)}</span></li>
        ))}</ul>
      )}
    </section>
  );
}
