"use client";

import { Markdown, MdInline } from "@/components/Markdown";
import { cell, colOf, tableWith } from "@/lib/team";
import { F, fmt, goalsOf, planSection, type Kpi, type Metrics } from "./model";
import { Card, H2, Loading, NoData, PageTitle, Progress, TeamUnavailable, useCentre } from "./ui";

/** The live figure for a KPI of team/README.md: users from /v1/admin/metrics, paying clients from real payments. */
export function liveValue(name: string, m: Metrics | null): { value: number; note: string } | null {
  if (!m) return null;
  if (/пользоват/i.test(name)) {
    return { value: m.totals.users, note: `аккаунты на сайте и в боте без тестовых; из них начали дело — ${fmt(m.totals.users_with_case)}` };
  }
  if (/плат/i.test(name) && m.payments) {
    return { value: m.payments.paid_clients, note: `клиенты с подтверждённой оплатой; оплаченных счетов — ${fmt(m.payments.paid)}, из них тарифов — ${fmt(m.payments.paid_plans)}` };
  }
  return null;
}

/** Day of the KPI month: it starts with the owner's KPI decision (team/decisions.md). */
export function monthDay(start: Date | null, days: number | null): { day: number; left: number; end: Date } | null {
  if (!start || !days) return null;
  const now = new Date();
  const d0 = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const day = Math.floor((d0.getTime() - start.getTime()) / 86_400_000) + 1;
  const end = new Date(start.getTime() + (days - 1) * 86_400_000);
  return { day: Math.max(1, Math.min(day, days)), left: Math.max(0, days - day), end };
}

export function Goal({ k, m, left }: { k: Kpi; m: Metrics | null; left: number | null }) {
  const v = liveValue(k.name, m);
  const pace = v && k.target != null && left ? Math.ceil(Math.max(0, k.target - v.value) / Math.max(1, left)) : null;
  return (
    <Card className="space-y-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-[17px] font-semibold">{k.name}</p>
        <p className="text-[15px] text-muted">цель {fmt(k.target)}</p>
      </div>
      <p className="text-[34px] leading-none font-semibold tabular-nums">{v ? fmt(v.value) : <NoData />}</p>
      <Progress value={v?.value ?? 0} max={k.target ?? 0} />
      <div className="space-y-1 text-[15px] text-muted">
        {v && k.target ? <p>{((v.value / k.target) * 100).toLocaleString("ru-RU", { maximumFractionDigits: 3 })} % цели</p> : null}
        {pace != null && <p>Нужно в среднем <b className="text-ink">{fmt(pace)}</b> в день до конца месяца</p>}
        {v && <p>{v.note}</p>}
        {k.how && <p>Как считаем: <MdInline text={k.how} /></p>}
      </div>
    </Card>
  );
}

export function Goals() {
  const c = useCentre();
  const { bundle, metrics: m } = c;
  if (c.teamError) return <div className="space-y-6"><PageTitle>Цели и курс</PageTitle><TeamUnavailable /></div>;
  if (!bundle) return <div className="space-y-6"><PageTitle>Цели и курс</PageTitle><Loading /></div>;
  const g = goalsOf(bundle);
  const day = monthDay(g.start, g.days);
  const sources = tableWith(planSection(bundle, /Математика/i)?.body, /^Источник$/i);
  const week = planSection(bundle, /Первая неделя/i);
  const product = planSection(bundle, /Задачи продукту/i);
  const sell = planSection(bundle, /Что продаём/i);
  const srcCol = sources ? colOf(sources, /^Источник$/i) : -1;
  const tgtCol = sources ? colOf(sources, /Цель/i) : -1;
  const referral = m?.referral;

  return (
    <div className="space-y-8">
      <PageTitle sub={day
        ? `День ${day.day} из ${g.days} · осталось ${day.left} дн. · до ${day.end.toLocaleDateString("ru-RU")}`
        : "Начало месяца KPI не найдено в decisions.md"}>
        Цели и курс
      </PageTitle>

      <section className="space-y-3">
        <H2>KPI владельца на месяц</H2>
        {g.kpis.length === 0 ? <p className="text-muted">В team/README.md нет таблицы целей.</p> : (
          <div className="grid gap-3 md:grid-cols-2">{g.kpis.map((k) => <Goal key={k.name} k={k} m={m} left={day?.left ?? null} />)}</div>
        )}
      </section>

      <section className="space-y-3">
        <H2>Откуда придут пользователи</H2>
        <p className="text-[15px] text-muted">План команды (plan-month-1.md) — оценки, пересматриваются еженедельно. Факт по каналам — из метрик.</p>
        {sources && srcCol >= 0 ? (
          <ul className="space-y-2">
            {sources.rows.map((r, i) => (
              <Card as="li" key={i} className="flex items-baseline justify-between gap-3">
                <span className="text-[16px]"><MdInline text={cell(r, srcCol)} /></span>
                <span className="shrink-0 text-[17px] font-semibold tabular-nums">{cell(r, tgtCol)}</span>
              </Card>
            ))}
          </ul>
        ) : <p className="text-muted">нет данных</p>}
        <Card className="space-y-1 text-[16px]">
          <p className="font-semibold">Рефералы сейчас</p>
          {referral ? (
            <>
              <p>Пришли по приглашению: <b>{fmt(referral.referred_users)}</b> · оплатили: <b>{fmt(referral.referred_paid ?? 0)}</b> · пригласивших: <b>{fmt(referral.inviters)}</b></p>
              <p>K-фактор: <b>{referral.k_factor == null ? "нет данных" : referral.k_factor.toLocaleString("ru-RU")}</b></p>
              {Object.keys(referral.sources).length > 0 && (
                <p className="text-muted">Каналы: {Object.entries(referral.sources).map(([k, v]) => `${k} — ${fmt(v)}`).join(", ")}</p>
              )}
            </>
          ) : <NoData />}
        </Card>
      </section>

      {week && (
        <section className="space-y-3">
          <H2>Вехи: {week.heading.replace(/^\d+\.\s*/, "")}</H2>
          <Card><Markdown doc text={week.body} base="team/" onFile={c.openFile} /></Card>
        </section>
      )}
      {product && (
        <section className="space-y-3">
          <H2>{product.heading.replace(/^\d+\.\s*/, "")}</H2>
          <Card><Markdown doc text={product.body} base="team/" onFile={c.openFile} /></Card>
        </section>
      )}
      {sell && (
        <section className="space-y-3">
          <H2>{sell.heading.replace(/^\d+\.\s*/, "")}</H2>
          <Card><Markdown doc text={sell.body} base="team/" onFile={c.openFile} /></Card>
        </section>
      )}
      <button type="button" onClick={() => c.openFile(F.plan)} className="text-[16px] font-semibold text-brand">Весь план на месяц</button>
    </div>
  );
}
