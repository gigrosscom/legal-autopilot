"use client";

import { MdInline } from "@/components/Markdown";
import { fmt, goalsOf, latestReport, moneyText, pendingOf, usd } from "./model";
import { PaymentsToConfirm } from "./Payments";
import { Card, H2, Loading, NoData, PageTitle, Progress, RowLink, Stat, TeamUnavailable, useCentre } from "./ui";
import { liveValue, monthDay } from "./Goals";

export function Summary() {
  const c = useCentre();
  const { metrics: m, bundle } = c;
  const pending = pendingOf(bundle);
  const report = latestReport(bundle);
  const goals = goalsOf(bundle);
  const day = monthDay(goals.start, goals.days);
  const today = new Date().toLocaleDateString("ru-RU", { weekday: "long", day: "numeric", month: "long" });

  return (
    <div className="space-y-8">
      <PageTitle sub={<span className="first-letter:uppercase">{today}{m ? ` · данные на ${new Date(m.generated_at).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}` : ""}</span>}>
        Сводка
      </PageTitle>

      {/* where we are heading: the month's KPI with live progress */}
      {goals.kpis.length > 0 && (
        <button type="button" onClick={() => c.go("goals")} className="block w-full rounded-2xl bg-sand p-4 text-start hover:bg-sand-deep">
          <div className="flex items-baseline justify-between gap-3">
            <p className="text-[17px] font-semibold">Цель месяца</p>
            <p className="text-[15px] text-muted">{day ? `день ${day.day} из ${goals.days} · осталось ${day.left}` : "сроки: нет данных"}</p>
          </div>
          <div className="mt-3 space-y-3">
            {goals.kpis.map((k) => {
              const v = liveValue(k.name, m);
              return (
                <div key={k.name}>
                  <div className="flex items-baseline justify-between gap-3 text-[15px]">
                    <span>{k.name}</span>
                    <span className="tabular-nums"><b className="text-[17px]">{v == null ? "нет данных" : fmt(v.value)}</b> <span className="text-muted">из {fmt(k.target)}</span></span>
                  </div>
                  <div className="mt-1.5"><Progress value={v?.value ?? 0} max={k.target ?? 0} /></div>
                </div>
              );
            })}
          </div>
        </button>
      )}

      <section className="space-y-3">
        <H2>Цифры</H2>
        {c.metricsError && <p role="alert" className="text-danger">{c.metricsError}</p>}
        {!m && !c.metricsError && <Loading />}
        {m && (
          <dl className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Stat label="Пользователи" value={fmt(m.totals.users)} note={m.today ? `сегодня +${fmt(m.today.users)}` : undefined} />
            <Stat label="Начали дело" value={fmt(m.totals.users_with_case)} note={`дел всего: ${fmt(m.totals.cases)}${m.today ? `, сегодня +${fmt(m.today.cases)}` : ""}`} />
            <Stat label="Документы" value={fmt(m.totals.documents)} note={m.today ? `сегодня +${fmt(m.today.documents)}` : undefined} />
            <Stat label="Оплачено" value={m.payments ? fmt(m.payments.paid) : <NoData />}
              note={m.payments ? `клиентов: ${fmt(m.payments.paid_clients)} · сегодня +${fmt(m.payments.paid_today)}` : undefined} />
            <Stat label="Выручка" value={m.payments ? moneyText(m.payments.revenue) : <NoData />}
              note={m.payments ? `сегодня: ${moneyText(m.payments.revenue_today)}` : undefined} />
            <Stat label="Заявки юристов" value={fmt(m.totals.lawyer_applications)} />
            <Stat label="Claude сегодня" value={m.claude ? usd(m.claude.today_usd) : <NoData />}
              note={m.claude ? `лимит ${usd(m.claude.daily_budget_usd)}` : undefined}
              tone={m.claude && m.claude.today_usd >= m.claude.daily_budget_usd ? "warn" : undefined} />
            <Stat label="Claude за месяц" value={m.claude ? usd(m.claude.month_usd) : <NoData />}
              note={m.claude ? `лимит ${usd(m.claude.monthly_budget_usd)}` : undefined}
              tone={m.claude && m.claude.month_usd >= m.claude.monthly_budget_usd ? "warn" : undefined} />
          </dl>
        )}
      </section>

      <PaymentsToConfirm compact />

      <section className="space-y-3">
        <H2 count={bundle ? pending.length : undefined}
          action={pending.length > 4 ? <button type="button" onClick={() => c.go("decisions")} className="text-[15px] font-semibold text-brand">Все</button> : undefined}>
          Что ждёт вашего решения
        </H2>
        {c.teamError ? <TeamUnavailable /> : !bundle ? <Loading /> : pending.length === 0 ? <p className="text-muted">Сейчас ничего.</p> : (
          <ul className="space-y-2">
            {pending.slice(0, 4).map((p, i) => (
              <Card as="li" key={i}>
                <p className="text-[14px] font-medium text-muted">{p.from}</p>
                <p className="mt-0.5 line-clamp-4 text-[16px]"><MdInline text={p.text} /></p>
              </Card>
            ))}
          </ul>
        )}
      </section>

      {report && (
        <section className="space-y-3">
          <H2>Последний отчёт</H2>
          <RowLink icon="document" title={report.text.match(/^#\s+(.*)$/m)?.[1] ?? report.title} sub={report.title}
            onClick={() => c.openFile(report.path)} />
        </section>
      )}
    </div>
  );
}

