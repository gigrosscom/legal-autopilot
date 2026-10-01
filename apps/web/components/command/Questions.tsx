"use client";

import { useCallback, useEffect, useState } from "react";
import { adminApi, errorText } from "@/lib/api";
import { Chip, Loading, PageTitle, useCentre } from "./ui";

type Ticket = { id: number; kind: string; status: string; created_at: string; case_id: string | null; name: string | null;
  email: string | null; phone: string | null; messages: { id: number; author: string; text: string; created_at: string }[] };
export type TicketsBoard = { columns: { id: string; label: string; cards: Ticket[] }[] };
const KIND: Record<string, string> = { question: "вопрос", complaint: "жалоба", suggestion: "предложение", plan: "тариф" };

/** Owner 01.10: the clients' questions to the desk as a board. Replies are written on the clients desk («Операции»). */
export function Questions() {
  const { token, go } = useCentre();
  const [b, setB] = useState<TicketsBoard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [col, setCol] = useState("new");
  const load = useCallback(() => adminApi<TicketsBoard>("/v1/admin/tickets", token).then((r) => { setB(r); setError(null); })
    .catch((e) => setError(errorText(e))), [token]);
  useEffect(() => { load(); }, [load]);
  async function move(id: number, status: string) {
    try { await adminApi(`/v1/admin/tickets/${id}/status`, token, { method: "POST", body: JSON.stringify({ status }) }); await load(); }
    catch (e) { setError(errorText(e)); }
  }

  return (
    <div className="space-y-6">
      <PageTitle sub="Обращения клиентов со страницы «Поддержка»">Вопросы</PageTitle>
      {error && <p role="alert" className="text-danger">{error}</p>}
      {!b && !error && <Loading />}
      {b && (
        <>
          <div className="flex gap-2 overflow-x-auto pb-1 lg:hidden">
            {b.columns.map((c) => (
              <button key={c.id} type="button" onClick={() => setCol(c.id)} aria-pressed={col === c.id}
                className={`min-h-10 shrink-0 rounded-full px-3.5 text-[15px] ${col === c.id ? "bg-action font-semibold text-white" : "bg-sand"}`}>{c.label} · {c.cards.length}</button>
            ))}
          </div>
          <div className="flex gap-3 overflow-x-auto pb-2">
            {b.columns.map((c) => (
              <section key={c.id} aria-label={c.label} className={`w-full shrink-0 space-y-2 rounded-2xl bg-sand p-2.5 lg:block lg:w-72 ${col === c.id ? "block" : "hidden"}`}>
                <h2 className="flex items-baseline justify-between px-1 text-[15px] font-semibold">{c.label}<span className="text-muted tabular-nums">{c.cards.length}</span></h2>
                <ul className="space-y-2">
                  {c.cards.map((t) => {
                    const last = t.messages.at(-1);
                    return (
                      <li key={t.id} className="space-y-2 rounded-xl bg-surface p-3 shadow-[0_1px_2px_rgb(0_0_0/0.06)] ring-1 ring-ink/[0.05]">
                        <div className="flex flex-wrap gap-1.5"><Chip tone="blue">№{t.id} · {KIND[t.kind] ?? t.kind}</Chip>
                          <Chip>{new Date(t.created_at).toLocaleDateString("ru-RU", { day: "numeric", month: "short" })}</Chip></div>
                        <p className="text-[14px] text-muted">{[t.name, t.email, t.phone].filter(Boolean).join(" · ") || "контакт не указан"}</p>
                        {last && <p className="line-clamp-4 text-[15px]">{last.author === "desk" ? "Ответ: " : ""}{last.text}</p>}
                        <div className="flex flex-wrap gap-2">
                          {c.id !== "in_progress" && c.id !== "done" && <button type="button" onClick={() => move(t.id, "in_progress")} className="min-h-9 rounded-full bg-sand px-3 text-[14px]">В работу</button>}
                          {c.id !== "done" && <button type="button" onClick={() => move(t.id, "done")} className="min-h-9 rounded-full bg-sand px-3 text-[14px]">Закрыть</button>}
                          {c.id === "done" && <button type="button" onClick={() => move(t.id, "in_progress")} className="min-h-9 rounded-full bg-sand px-3 text-[14px]">Открыть снова</button>}
                          <button type="button" onClick={() => go("ops")} className="min-h-9 rounded-full px-3 text-[14px] text-action">Ответить</button>
                        </div>
                      </li>
                    );
                  })}
                  {c.cards.length === 0 && <li className="px-1 py-2 text-[14px] text-muted">пусто</li>}
                </ul>
              </section>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
