"use client";

import { useEffect, useState } from "react";
import { MdInline } from "@/components/Markdown";
import { adminApi } from "@/lib/api";
import type { DealsBoard } from "./Deals";
import { backlog, fmt, goalsOf, latestReport, moneyText, pendingOf, secs, usd } from "./model";
import type { TicketsBoard } from "./Questions";
import { PaymentsToConfirm } from "./Payments";
import { ReviewsToCheck } from "./Reviews";
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

      <BoardTiles />

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
            <Stat label="Ждут подтверждения" value={m.payments ? fmt(m.payments.awaiting_confirmation) : <NoData />}
              note="оплаты" tone={m.payments && m.payments.awaiting_confirmation > 0 ? "warn" : undefined} />
            <Stat label="Claude сегодня" value={m.claude ? usd(m.claude.today_usd) : <NoData />}
              note={m.claude ? `лимит ${usd(m.claude.daily_budget_usd)}` : undefined}
              tone={m.claude && m.claude.today_usd >= m.claude.daily_budget_usd ? "warn" : undefined} />
            <Stat label="Claude за месяц" value={m.claude ? usd(m.claude.month_usd) : <NoData />}
              note={m.claude ? `лимит ${usd(m.claude.monthly_budget_usd)}` : undefined}
              tone={m.claude && m.claude.month_usd >= m.claude.monthly_budget_usd ? "warn" : undefined} />
            {/* the owner's target (30.09): the first words of an answer within 2 s */}
            <Stat label="Ответ чата: первые слова p50/p95"
              value={m.chat_latency?.n ? `${secs(m.chat_latency.p50_ms)} / ${secs(m.chat_latency.p95_ms)}` : <NoData />}
              note={m.chat_latency?.n ? `ответов за 24 ч: ${fmt(m.chat_latency.n)} · ${Object.entries(m.chat_latency.by_provider)
                .map(([p, v]) => `${p} ${secs(v.p50_ms)}`).join(", ")}` : undefined}
              tone={m.chat_latency?.p50_ms != null && m.chat_latency.p50_ms > 2000 ? "warn" : undefined} />
          </dl>
        )}
      </section>

      <ReviewsToCheck compact />
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


/** Owner 01.10: the three boards at a glance, and what waits for the owner (payments to confirm, documents to check). */
function BoardTiles() {
  const c = useCentre();
  const [deals, setDeals] = useState<DealsBoard | null>(null);
  const [tickets, setTickets] = useState<TicketsBoard | null>(null);
  useEffect(() => {
    adminApi<DealsBoard>("/v1/admin/deals", c.token).then(setDeals).catch(() => setDeals(null));
    adminApi<TicketsBoard>("/v1/admin/tickets", c.token).then(setTickets).catch(() => setTickets(null));
  }, [c.token]);
  const tasks = backlog(c.bundle);
  const count = (b: { columns: { id: string; cards: unknown[] }[] } | null, ids: string[]) =>
    b ? b.columns.filter((x) => ids.includes(x.id)).reduce((n, x) => n + x.cards.length, 0) : null;
  const tile = "block w-full rounded-2xl bg-sand p-4 text-start hover:bg-sand-deep";
  const waiting = deals?.waiting_for_owner ?? 0;
  return (
    <section className="space-y-3">
      {waiting > 0 && (
        <button type="button" onClick={() => c.go("deals")} className="block w-full rounded-2xl bg-warning-50 p-4 text-start text-[17px] font-semibold">
          Ждёт вашего действия: {waiting} — оплаты к подтверждению и документы на проверку
        </button>
      )}
      <div className="grid gap-3 sm:grid-cols-3">
        <button type="button" onClick={() => c.go("deals")} className={tile}>
          <p className="text-[15px] text-muted">Сделки в работе</p>
          <p className="text-[28px] font-semibold tabular-nums">{count(deals, ["new", "intake", "to_pay", "confirm", "paid", "ready", "sent"]) ?? "—"}</p>
          <p className="text-[14px] text-muted">{deals ? `оплачено за 7 дней: ${Math.round(deals.paid_week).toLocaleString("ru-RU")} ₸` : ""}</p>
        </button>
        <button type="button" onClick={() => c.go("questions")} className={tile}>
          <p className="text-[15px] text-muted">Вопросы клиентов</p>
          <p className="text-[28px] font-semibold tabular-nums">{count(tickets, ["new", "in_progress"]) ?? "—"}</p>
          <p className="text-[14px] text-muted">новые и в работе</p>
        </button>
        <button type="button" onClick={() => c.go("tasks")} className={tile}>
          <p className="text-[15px] text-muted">Задачи команды</p>
          <p className="text-[28px] font-semibold tabular-nums">{c.bundle ? tasks.filter((t) => t.state !== "done").length : "—"}</p>
          <p className="text-[14px] text-muted">{c.bundle ? `ждут вас: ${tasks.filter((t) => t.state === "waiting").length}` : ""}</p>
        </button>
      </div>
    </section>
  );
}
