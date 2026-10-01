"use client";

import { useCallback, useEffect, useState } from "react";
import { Icon } from "@/components/ui";
import { adminApi, API_URL, errorText } from "@/lib/api";
import { Chip, Loading, PageTitle, Stat, useCentre } from "./ui";

type Doc = { id: string; action_id: string; status: string; pdf: boolean; docx: boolean };
export type Deal = {
  id: string; column: string; title: string | null; status_label: string; amount_at_stake: number | null; currency: string;
  created_at: string; updated_at: string | null; deadline: string | null; pending_review: string[]; documents: Doc[];
  bill: { code: string; status: string; amount: number; purpose: string } | null;
  client: { name: string; contacts: string[]; channel: string | null; ecp: boolean };
};
export type DealsBoard = { columns: { id: string; label: string; cards: Deal[] }[]; paid_today: number; paid_week: number;
  currency: string; waiting_for_owner: number };

const money = (n: number) => `${Math.round(n).toLocaleString("ru-RU")} ₸`;
const day = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString("ru-RU", { day: "numeric", month: "short" }) : "");
const BILL: Record<string, string> = { pending: "счёт выставлен", awaiting_confirmation: "ждёт подтверждения",
  paid: "оплачено", not_found: "оплата не найдена" };
const NEXT: Record<string, string> = { new: "ждём, когда ИИ определит сценарий", intake: "клиент дополняет черновик",
  to_pay: "клиент оплачивает", confirm: "подтвердите оплату в «Операциях»", paid: "документ готовится или ждёт вашей проверки",
  ready: "клиент подписывает и отправляет", sent: "ждём ответ адресата", closed: "—" };

/** Owner 01.10: every real client's deal on one board, from the first question to the answer. */
export function Deals() {
  const { token } = useCentre();
  const [b, setB] = useState<DealsBoard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [col, setCol] = useState("to_pay");
  const [open, setOpen] = useState<Deal | null>(null);
  const load = useCallback(() => adminApi<DealsBoard>("/v1/admin/deals", token).then((r) => { setB(r); setError(null); })
    .catch((e) => setError(errorText(e))), [token]);
  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-6">
      <PageTitle sub="Реальные клиенты (без тестовых): от первого вопроса до ответа адресата">Сделки</PageTitle>
      {error && <p role="alert" className="text-danger">{error}</p>}
      {!b && !error && <Loading />}
      {b && (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Stat label="Оплачено сегодня" value={money(b.paid_today)} />
            <Stat label="Оплачено за 7 дней" value={money(b.paid_week)} />
            <Stat label="Ждёт вашего действия" value={b.waiting_for_owner} tone={b.waiting_for_owner ? "warn" : undefined} />
            <Stat label="Всего сделок" value={b.columns.reduce((n, c) => n + c.cards.length, 0)} />
          </div>
          {/* phone: one column at a time */}
          <div className="flex gap-2 overflow-x-auto pb-1 lg:hidden">
            {b.columns.map((c) => (
              <button key={c.id} type="button" onClick={() => setCol(c.id)} aria-pressed={col === c.id}
                className={`min-h-10 shrink-0 rounded-full px-3.5 text-[15px] ${col === c.id ? "bg-action font-semibold text-white" : "bg-sand"}`}>
                {c.label} · {c.cards.length}
              </button>
            ))}
          </div>
          <div className="flex gap-3 overflow-x-auto pb-2">
            {b.columns.map((c) => (
              <section key={c.id} aria-label={c.label}
                className={`w-full shrink-0 space-y-2 rounded-2xl bg-sand p-2.5 lg:block lg:w-72 ${col === c.id ? "block" : "hidden"}`}>
                <h2 className="flex items-baseline justify-between px-1 text-[15px] font-semibold">{c.label}<span className="text-muted tabular-nums">{c.cards.length}</span></h2>
                <ul className="space-y-2">
                  {c.cards.map((d) => (
                    <li key={d.id}>
                      <button type="button" onClick={() => setOpen(d)}
                        className="w-full space-y-1.5 rounded-xl bg-surface p-3 text-start shadow-[0_1px_2px_rgb(0_0_0/0.06)] ring-1 ring-ink/[0.05] hover:ring-action">
                        <p className="text-[15px] font-semibold leading-snug">{d.title || "Без сценария"}</p>
                        <p className="text-[14px] text-muted">{d.client.name || d.client.contacts[0] || "контакт не указан"} · {day(d.created_at)}</p>
                        <div className="flex flex-wrap gap-1.5">
                          {d.amount_at_stake != null && <Chip>спор {money(d.amount_at_stake)}</Chip>}
                          {d.bill && <Chip tone={d.bill.status === "paid" ? "done" : d.bill.status === "awaiting_confirmation" ? "warn" : "blue"}>{d.bill.code} · {money(d.bill.amount)}</Chip>}
                          {d.pending_review.length > 0 && <Chip tone="warn">на проверке</Chip>}
                          {d.deadline && <Chip>срок {day(d.deadline)}</Chip>}
                        </div>
                      </button>
                    </li>
                  ))}
                  {c.cards.length === 0 && <li className="px-1 py-2 text-[14px] text-muted">пусто</li>}
                </ul>
              </section>
            ))}
          </div>
        </>
      )}
      {open && <DealDetail deal={open} onClose={() => setOpen(null)} />}
    </div>
  );
}

type Fact = { field: string; label: string; value: string };
type CaseFull = { id: string; facts?: Fact[]; evidence?: { id: string; filename: string; kind: string }[]; status: string;
  log?: { from: string; text: string; at?: string }[] };

function DealDetail({ deal, onClose }: { deal: Deal; onClose: () => void }) {
  const { token } = useCentre();
  const [c, setC] = useState<CaseFull | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [edit, setEdit] = useState<Record<string, string>>({});
  const [saved, setSaved] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => adminApi<CaseFull>(`/v1/admin/cases/${deal.id}`, token).then(setC).catch((e) => setError(errorText(e))), [deal.id, token]);
  useEffect(() => { load(); }, [load]);

  // the owner corrects the data (a wrong name, the client's own e-mail as the seller's): the documents are made again
  async function saveFacts() {
    setBusy(true); setError(null); setSaved(null);
    try {
      const r = await adminApi<{ rebuilt: number }>(`/v1/admin/cases/${deal.id}/facts`, token,
        { method: "POST", body: JSON.stringify({ values: edit, rebuild: true }) });
      setEdit({});
      setSaved(r.rebuilt ? `Сохранено, документ пересобран (${r.rebuilt})` : "Сохранено");
      await load();
    } catch (e) { setError(errorText(e)); } finally { setBusy(false); }
  }

  async function download(d: Doc, fmt: "pdf" | "docx") {
    try {
      const res = await fetch(`${API_URL}/v1/admin/actions/${d.id}/document?format=${fmt}`, { headers: { "X-Admin-Token": token } });
      if (!res.ok) throw new Error(String(res.status));
      const url = URL.createObjectURL(await res.blob());
      Object.assign(document.createElement("a"), { href: url, download: `${d.action_id}.${fmt}` }).click();
      setTimeout(() => URL.revokeObjectURL(url), 10_000);
    } catch (e) { setError(errorText(e)); }
  }

  return (
    <div role="dialog" aria-modal="true" aria-label={deal.title ?? "Сделка"} className="fixed inset-0 z-50 flex justify-end">
      <button type="button" aria-label="Закрыть" onClick={onClose} className="absolute inset-0 bg-ink/40" />
      <div className="relative h-full w-full max-w-xl space-y-5 overflow-y-auto bg-surface p-5 pt-[calc(1.25rem+env(safe-area-inset-top))]">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-[20px] font-semibold leading-snug">{deal.title || "Без сценария"}</p>
            <p className="text-[15px] text-muted">{deal.status_label} · дело {deal.id.slice(0, 8)} · создано {day(deal.created_at)}</p>
          </div>
          <button type="button" onClick={onClose} aria-label="Закрыть" className="flex h-10 w-10 items-center justify-center rounded-full hover:bg-sand"><Icon name="x" size={22} /></button>
        </div>
        <section className="space-y-1">
          <h3 className="font-semibold">Клиент</h3>
          <p>{deal.client.name || "имя не указано"}{deal.client.ecp ? " · вход по ЭЦП" : ""}{deal.client.channel ? ` · ${deal.client.channel}` : ""}</p>
          {deal.client.contacts.length ? deal.client.contacts.map((x) => <p key={x} className="text-[15px]">{x}</p>)
            : <p className="text-[15px] text-muted">контакт не подтверждён</p>}
        </section>
        <section className="space-y-1">
          <h3 className="font-semibold">Оплата и следующий шаг</h3>
          <p className="text-[15px]">{deal.bill ? `${deal.bill.code} · ${money(deal.bill.amount)} · ${BILL[deal.bill.status] ?? deal.bill.status}` : "счёта нет"}</p>
          <p className="text-[15px] text-muted">Дальше: {NEXT[deal.column] ?? "—"}{deal.deadline ? ` · срок ${day(deal.deadline)}` : ""}</p>
        </section>
        {deal.documents.length > 0 && (
          <section className="space-y-2">
            <h3 className="font-semibold">Документы</h3>
            {deal.documents.map((d) => (
              <div key={d.id} className="flex flex-wrap items-center gap-2">
                <span className="flex-1 text-[15px]">{d.action_id} · {d.status}</span>
                {d.pdf && <button type="button" onClick={() => download(d, "pdf")} className="min-h-9 rounded-full bg-sand px-3 text-[14px] font-medium">PDF</button>}
                {d.docx && <button type="button" onClick={() => download(d, "docx")} className="min-h-9 rounded-full bg-sand px-3 text-[14px] font-medium">DOCX</button>}
              </div>
            ))}
          </section>
        )}
        {error && <p role="alert" className="text-danger">{error}</p>}
        {!c && !error && <Loading />}
        {c?.facts && c.facts.length > 0 && (
          <section className="space-y-1">
            <h3 className="font-semibold">Данные дела</h3>
            <dl className="grid grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)] gap-x-3 gap-y-1 text-[15px]">
              {c.facts.map((f) => [<dt key={`${f.field}-l`} className="text-muted">{f.label}</dt>, (
                <dd key={`${f.field}-v`}>
                  {f.field in edit
                    ? <input aria-label={f.label} value={edit[f.field]} onChange={(e) => setEdit((x) => ({ ...x, [f.field]: e.target.value }))}
                        className="w-full rounded-lg bg-sand px-2 py-1" placeholder="пусто — убрать" />
                    : <>{f.value} <button type="button" onClick={() => setEdit((x) => ({ ...x, [f.field]: String(f.value ?? "") }))}
                        className="ms-1 text-[13px] text-action">исправить</button></>}
                </dd>
              )])}
            </dl>
            {Object.keys(edit).length > 0 && (
              <div className="flex gap-2 pt-2">
                <button type="button" disabled={busy} onClick={saveFacts} className="min-h-10 rounded-full bg-action px-4 text-[15px] font-semibold text-white disabled:opacity-50">Сохранить и пересобрать документ</button>
                <button type="button" onClick={() => setEdit({})} className="min-h-10 rounded-full bg-sand px-4 text-[15px]">Отмена</button>
              </div>
            )}
            {saved && <p role="status" className="text-[15px] text-success">{saved}</p>}
          </section>
        )}
        {c?.evidence && c.evidence.length > 0 && (
          <section className="space-y-1">
            <h3 className="font-semibold">Файлы клиента</h3>
            {c.evidence.map((e) => <p key={e.id} className="text-[15px]">{e.filename || e.kind}</p>)}
          </section>
        )}
      </div>
    </div>
  );
}
