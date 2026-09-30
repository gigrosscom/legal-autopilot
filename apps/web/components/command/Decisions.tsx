"use client";

import { useMemo, useState } from "react";
import { MdInline } from "@/components/Markdown";
import { plain } from "@/lib/team";
import { decisionsOf, F, pendingOf } from "./model";
import { Card, H2, Loading, PageTitle, TeamUnavailable, useCentre } from "./ui";

const KIND = { session: "Сессия", task: "Бэклог", report: "Отчёт" } as const;

/** «Ждёт вашего решения» (sessions, backlog, the latest report) and the owner's decisions, newest first. */
export function Decisions() {
  const c = useCentre();
  const decisions = useMemo(() => decisionsOf(c.bundle), [c.bundle]);
  const pending = useMemo(() => pendingOf(c.bundle), [c.bundle]);
  const [q, setQ] = useState("");
  if (c.teamError) return <div className="space-y-6"><PageTitle>Решения</PageTitle><TeamUnavailable /></div>;
  if (!c.bundle) return <div className="space-y-6"><PageTitle>Решения</PageTitle><Loading /></div>;
  const needle = q.trim().toLowerCase();
  const shown = needle ? decisions.filter((d) => plain(`${d.date} ${d.text} ${d.source}`).toLowerCase().includes(needle)) : decisions;

  return (
    <div className="space-y-8">
      <PageTitle sub="Решение записывается в decisions.md — это общая память всех сессий.">Решения</PageTitle>

      <section className="space-y-3">
        <H2 count={pending.length}>Ждёт вашего решения</H2>
        {pending.length === 0 ? <p className="text-muted">Сейчас ничего.</p> : (
          <ul className="space-y-2">
            {pending.map((p, i) => (
              <Card as="li" key={i} className="border-s-4 border-action">
                <p className="text-[14px] font-medium text-muted">{KIND[p.kind]} · {p.from}</p>
                <p className="mt-0.5 text-[16px]"><MdInline text={p.text} base="team/" onFile={c.openFile} /></p>
              </Card>
            ))}
          </ul>
        )}
      </section>

      <section className="space-y-3">
        <H2 count={decisions.length}>Принятые решения</H2>
        <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Поиск по решениям"
          className="min-h-12 w-full rounded-full bg-sand px-5 text-[17px] outline-none placeholder:text-muted focus:ring-2 focus:ring-accent" />
        {shown.length === 0 && <p className="text-muted">{decisions.length ? "Ничего не найдено." : "В decisions.md нет таблицы решений."}</p>}
        <ol className="space-y-2">
          {shown.map((d, i) => (
            <Card as="li" key={i}>
              <p className="text-[14px] font-semibold text-brand-dark tabular-nums">{d.date}<span className="font-normal text-muted"> · {d.source}</span></p>
              <p className="mt-1 text-[16px] leading-relaxed"><MdInline text={d.text} base="team/" onFile={c.openFile} /></p>
            </Card>
          ))}
        </ol>
        <button type="button" onClick={() => c.openFile(F.decisions)} className="text-[16px] font-semibold text-brand">Открыть decisions.md целиком</button>
      </section>
    </div>
  );
}
