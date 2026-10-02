"use client";

import { useCallback, useEffect, useState } from "react";
import { Icon } from "@/components/ui";
import { adminApi, API_URL, errorText } from "@/lib/api";
import { Chip, Loading, NoData, PageTitle, useCentre } from "./ui";

type DocRow = {
  id: string; created_at: string; case_id: string; case_short: string; service: string; action_id: string;
  client: string; test: boolean; pdf: boolean; docx: boolean; unlocked_by: string | null;
  bill: { code: string; amount: number; currency: string | null; status: string; label: string } | null;
};
type Page = { total: number; items: DocRow[] };

const PAGE = 50;
const money = (n: number) => `${Math.round(n).toLocaleString("ru-RU")} ₸`;
const when = (iso: string) => new Date(iso).toLocaleString("ru-RU", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
const TONE: Record<string, "done" | "warn" | "neutral"> = { paid: "done", awaiting_confirmation: "warn" };

/** Owner 01.10: every document made for an order, newest first — the case, the service, the client, the bill — and
 *  its PDF / DOCX. Filters «оплаченные», «сегодня»; search by the case number or the bill code. */
export function Documents() {
  const { token } = useCentre();
  const [paid, setPaid] = useState(false);
  const [today, setToday] = useState(false);
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(0);
  const [data, setData] = useState<Page | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    const p = new URLSearchParams({ limit: String(PAGE), offset: String(page * PAGE) });
    if (paid) p.set("paid", "true");
    if (today) p.set("today", "true");
    if (query) p.set("q", query);
    adminApi<Page>(`/v1/admin/documents?${p}`, token).then((r) => { setData(r); setError(null); }).catch((e) => setError(errorText(e)));
  }, [token, paid, today, query, page]);
  useEffect(() => { load(); }, [load]);

  async function download(d: DocRow, fmt: "pdf" | "docx") {
    try {
      const res = await fetch(`${API_URL}/v1/admin/actions/${d.id}/document?format=${fmt}`, { headers: { "X-Admin-Token": token } });
      if (!res.ok) throw new Error(String(res.status));
      const url = URL.createObjectURL(await res.blob());
      Object.assign(document.createElement("a"), { href: url, download: `${d.action_id}-${d.case_short}.${fmt}` }).click();
      setTimeout(() => URL.revokeObjectURL(url), 10_000);
    } catch (e) { setError(errorText(e)); }
  }

  const toggle = (on: boolean, set: (v: boolean) => void, label: string) => (
    <button type="button" aria-pressed={on} onClick={() => { set(!on); setPage(0); }}
      className={`min-h-10 rounded-full px-4 text-[15px] font-semibold ${on ? "bg-ink text-surface" : "bg-sand hover:bg-sand-deep"}`}>{label}</button>
  );
  const pages = data ? Math.max(1, Math.ceil(data.total / PAGE)) : 1;

  return (
    <div className="space-y-5">
      <PageTitle sub="Все документы по заказам, новые сверху">Документы</PageTitle>
      <div className="flex flex-wrap items-center gap-2">
        {toggle(paid, setPaid, "Оплаченные")}
        {toggle(today, setToday, "Сегодня")}
        <form className="flex w-full min-w-0 sm:ms-auto sm:w-auto sm:flex-1 sm:max-w-xs" onSubmit={(e) => { e.preventDefault(); setQuery(q.trim()); setPage(0); }}>
          <input value={q} onChange={(e) => setQ(e.target.value)} type="search" placeholder="Номер дела или код счёта"
            aria-label="Поиск по номеру дела или коду счёта" className="input min-h-10 rounded-full" />
        </form>
      </div>
      {error && <p role="alert" className="text-danger">{error}</p>}
      {!data && !error && <Loading />}
      {data && data.items.length === 0 && <NoData>Документов нет</NoData>}
      {data && data.items.length > 0 && (
        <ul className="divide-y divide-line overflow-hidden rounded-2xl bg-surface ring-1 ring-line">
          {data.items.map((d) => (
            <li key={d.id} className="grid gap-x-4 gap-y-1.5 p-4 lg:grid-cols-[8.5rem_1fr_13rem_auto] lg:items-center">
              <p className="text-[14px] text-muted tabular-nums">{when(d.created_at)}</p>
              <div className="min-w-0">
                <p className="truncate text-[16px] font-semibold">{d.service}</p>
                <p className="truncate text-[14px] text-muted">
                  <a href={`/ops?tab=deals&deal=${d.case_id}`} className="link font-mono">{d.case_short}</a>
                  {d.client && <> · {d.client}</>}{d.test && <> · тест</>}
                </p>
              </div>
              <div className="text-[14px]">
                {d.bill ? (
                  <span className="flex flex-wrap items-center gap-1.5">
                    <span className="font-mono">{d.bill.code}</span>
                    <span className="tabular-nums">{money(d.bill.amount)}</span>
                    <Chip tone={TONE[d.bill.status] ?? "neutral"}>{d.bill.label}</Chip>
                  </span>
                ) : <span className="text-muted">{d.unlocked_by === "free" ? "бесплатно" : d.unlocked_by ? `оплата: ${d.unlocked_by}` : "без счёта"}</span>}
              </div>
              <div className="flex gap-2">
                <button type="button" disabled={!d.pdf} onClick={() => download(d, "pdf")}
                  className="flex min-h-10 items-center gap-1.5 rounded-full bg-sand px-3.5 text-[14px] font-semibold hover:bg-sand-deep disabled:opacity-40">
                  <Icon name="download" size={16} />PDF</button>
                <button type="button" disabled={!d.docx} onClick={() => download(d, "docx")}
                  className="flex min-h-10 items-center gap-1.5 rounded-full bg-sand px-3.5 text-[14px] font-semibold hover:bg-sand-deep disabled:opacity-40">
                  <Icon name="download" size={16} />DOCX</button>
              </div>
            </li>
          ))}
        </ul>
      )}
      {data && pages > 1 && (
        <div className="flex items-center justify-center gap-3 text-[15px]">
          <button type="button" disabled={page === 0} onClick={() => setPage(page - 1)} className="min-h-10 rounded-full px-4 hover:bg-sand disabled:opacity-40">Назад</button>
          <span className="text-muted tabular-nums">{page + 1} из {pages}</span>
          <button type="button" disabled={page + 1 >= pages} onClick={() => setPage(page + 1)} className="min-h-10 rounded-full px-4 hover:bg-sand disabled:opacity-40">Дальше</button>
        </div>
      )}
    </div>
  );
}
