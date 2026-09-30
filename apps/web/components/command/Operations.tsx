"use client";

import { useState } from "react";
import { MetricsTab } from "@/components/MetricsTab";
import { OpsDesk } from "@/components/OpsDesk";
import { PaymentsToConfirm } from "./Payments";
import { ReviewsToCheck } from "./Reviews";
import { H2, PageTitle, RowLink, useCentre } from "./ui";

/** Everything the operations centre had: payments, the clients and lawyers desks, metrics, and the admin. */
export function Operations() {
  const { token } = useCentre();
  const [view, setView] = useState<"desk" | "metrics">("desk");
  return (
    <div className="space-y-8">
      <PageTitle sub="Проверка документов, оплаты, обращения клиентов и метрики.">Операции</PageTitle>
      <ReviewsToCheck />
      <PaymentsToConfirm />
      <section className="space-y-3">
        <div role="tablist" className="flex gap-2">
          {([["desk", "Клиенты и юристы"], ["metrics", "Метрики"]] as const).map(([k, label]) => (
            <button key={k} role="tab" aria-selected={view === k} onClick={() => setView(k)}
              className={`min-h-10 rounded-full px-4 text-[15px] font-semibold ${view === k ? "bg-ink text-white" : "bg-sand hover:bg-sand-deep"}`}>{label}</button>
          ))}
        </div>
        {view === "desk" ? <OpsDesk /> : <MetricsTab token={token} />}
      </section>
      <section className="space-y-3">
        <H2>Ещё</H2>
        <RowLink icon="shieldCheck" title="Админка: дела, проверка документов, ошибки" sub="/admin — тот же ключ администратора" href="/admin" />
      </section>
    </div>
  );
}
