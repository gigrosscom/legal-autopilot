"use client";

import { useCallback, useEffect, useState } from "react";
import { adminApi, API_URL, ApiError, errorText } from "@/lib/api";
import type { CourierStatus } from "@/lib/courier";
import { Card, Chip, H2, Loading, PageTitle, useCentre } from "./ui";

// Pilot «Курьер» (owner 01.10): the duty person orders the courier by hand, enters the track number and moves the
// status; the client sees each step in the case. API: team/api/courier.md (branch claude/ai-team).

type Delivery = {
  id: number; case_id: string; case_title: string | null; client_name: string | null; client_phone: string | null;
  status: CourierStatus; paid: boolean; pickup_address: string; pickup_date: string; pickup_window_label?: string | null;
  respondent_name: string; respondent_address: string; carrier: string | null; track_number: string | null;
  track_url: string | null; created_at: string; updated_at: string; answer_due_at: string | null; test?: boolean;
};
type List = { items: Delivery[]; counts: Partial<Record<CourierStatus, number>> };

const STATUS: Record<CourierStatus, string> = {
  awaiting_payment: "Ждёт оплаты", ordered: "Заказан", picked_up: "Забран", in_transit: "В пути",
  delivered: "Вручён", refused: "Отказ, акт", answered: "Ответ получен", cancelled: "Отменён",
};
// what the duty person does next; the client is told of every step
const NEXT: Partial<Record<CourierStatus, CourierStatus[]>> = {
  ordered: ["picked_up", "cancelled"], picked_up: ["in_transit"], in_transit: ["delivered", "refused"],
  delivered: ["answered"], refused: ["answered"],
};
// the buttons say what the duty person does
const ACTION: Partial<Record<CourierStatus, string>> = {
  picked_up: "Курьер забрал", in_transit: "Передан в доставку", delivered: "Вручён под роспись", refused: "Отказ — есть акт",
  answered: "Ответ получен", cancelled: "Отменить доставку",
};
const FILTERS: { key: string; label: string }[] = [
  { key: "active", label: "В работе" }, { key: "awaiting_payment", label: "Ждёт оплаты" }, { key: "ordered", label: "Заказан" },
  { key: "picked_up", label: "Забран" }, { key: "in_transit", label: "В пути" }, { key: "delivered", label: "Вручён" },
  { key: "refused", label: "Отказ" }, { key: "answered", label: "Ответ" }, { key: "all", label: "Все" },
];
const tone = (s: CourierStatus) => (s === "awaiting_payment" || s === "refused" ? "warn" : s === "answered" || s === "delivered" ? "done" : s === "cancelled" ? "neutral" : "blue");
const day = (iso: string) => new Date(`${iso.slice(0, 10)}T12:00:00`).toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit", weekday: "short" });

export function Deliveries() {
  const { token } = useCentre();
  const [filter, setFilter] = useState("active");
  const [list, setList] = useState<List | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => adminApi<List>(`/v1/admin/deliveries?status=${filter}`, token)
    .then((r) => { setList(r); setError(null); }).catch((e) => setError(errorText(e))), [token, filter]);
  useEffect(() => { load(); }, [load]);

  const counts = list?.counts ?? {};
  const active = Object.entries(counts).filter(([k]) => k !== "answered" && k !== "cancelled").reduce((n, [, v]) => n + (v ?? 0), 0);

  return (
    <div className="space-y-5">
      <PageTitle sub="Пилот «Курьер», Алматы, 3 990 ₸. Закажите курьера в службе, внесите трек-номер и двигайте статус — клиент видит каждый шаг в деле.">
        Доставки
      </PageTitle>
      <div role="tablist" aria-label="Статус доставки" className="flex gap-2 overflow-x-auto pb-1 lg:flex-wrap">
        {FILTERS.map((f) => {
          const n = f.key === "active" ? active : f.key === "all" ? undefined : counts[f.key as CourierStatus];
          return (
            <button key={f.key} type="button" role="tab" aria-selected={filter === f.key} onClick={() => setFilter(f.key)}
              className={`min-h-10 shrink-0 rounded-full px-3.5 text-[15px] ${filter === f.key ? "bg-ink text-surface font-semibold" : "bg-surface ring-1 ring-line"}`}>
              {f.label}{n ? <span className="ms-1.5 tabular-nums opacity-70">{n}</span> : null}
            </button>
          );
        })}
      </div>
      {error && <p role="alert" className="text-danger">{error}</p>}
      {!list && !error && <Loading />}
      {list && <H2 count={list.items.length}>{FILTERS.find((f) => f.key === filter)?.label}</H2>}
      {list?.items.length === 0 && <p className="text-muted">Доставок нет.</p>}
      <ul className="grid gap-3 lg:grid-cols-2">
        {list?.items.map((d) => <DeliveryCard key={d.id} d={d} onSaved={load} />)}
      </ul>
    </div>
  );
}

function DeliveryCard({ d, onSaved }: { d: Delivery; onSaved: () => void }) {
  const { token } = useCentre();
  const [carrier, setCarrier] = useState(d.carrier ?? "");
  const [track, setTrack] = useState(d.track_number ?? "");
  const [url, setUrl] = useState(d.track_url ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dirty = carrier !== (d.carrier ?? "") || track !== (d.track_number ?? "") || url !== (d.track_url ?? "");

  // a photo of the second copy with the respondent's mark, or the refusal act: the client sees it in the case
  async function proof(files: File[]) {
    setBusy(true);
    setError(null);
    try {
      const body = new FormData();
      files.forEach((f) => body.append("files", f));
      const r = await fetch(`${API_URL}/v1/admin/deliveries/${d.id}/proof`, { method: "POST", headers: { "X-Admin-Token": token }, body });
      if (!r.ok) throw new ApiError(r.status, { code: "proof_failed", message: "Файл не загрузился. Попробуйте ещё раз." });
      onSaved();
    } catch (e) { setError(errorText(e)); } finally { setBusy(false); }
  }

  async function save(body: Record<string, string>) {
    setBusy(true);
    setError(null);
    try {
      await adminApi(`/v1/admin/deliveries/${d.id}`, token, { method: "PATCH", body: JSON.stringify(body) });
      onSaved();
    } catch (e) { setError(errorText(e)); } finally { setBusy(false); }
  }

  return (
    <Card as="li" className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <Chip tone={tone(d.status)}>{STATUS[d.status]}</Chip>
          {!d.paid && d.status !== "awaiting_payment" && <Chip tone="warn">не оплачено</Chip>}
          {d.test && <Chip>тест</Chip>}
        </div>
        <a className="text-[15px] text-action underline" href={`/ops?tab=deals&deal=${d.case_id}`}>{d.case_title ?? "Дело"}</a>
      </div>
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-[15px]">
        <dt className="text-muted">Забрать</dt>
        <dd>{day(d.pickup_date)}{d.pickup_window_label ? `, ${d.pickup_window_label}` : ""} · {d.pickup_address}</dd>
        <dt className="text-muted">Клиент</dt>
        <dd>{d.client_name ?? "—"}{d.client_phone && <> · <a className="underline" href={`tel:${d.client_phone}`} dir="ltr">{d.client_phone}</a></>}</dd>
        <dt className="text-muted">Вручить</dt>
        <dd>{d.respondent_name} · {d.respondent_address}</dd>
        {d.answer_due_at && <><dt className="text-muted">Ответ до</dt><dd>{day(d.answer_due_at)}</dd></>}
      </dl>
      {d.status !== "awaiting_payment" && d.status !== "cancelled" && (
        <form className="grid gap-2 sm:grid-cols-[1fr_1fr]" onSubmit={(e) => { e.preventDefault(); save({ carrier: carrier.trim(), track_number: track.trim(), track_url: url.trim() }); }}>
          <label className="space-y-1 text-[13px] text-muted">
            <span>Служба</span>
            <input className="input" value={carrier} onChange={(e) => setCarrier(e.target.value)} placeholder="Алем ТАТ" />
          </label>
          <label className="space-y-1 text-[13px] text-muted">
            <span>Трек-номер</span>
            <input className="input font-mono" dir="ltr" value={track} onChange={(e) => setTrack(e.target.value)} placeholder="AT123456789" />
          </label>
          <label className="space-y-1 text-[13px] text-muted sm:col-span-2">
            <span>Ссылка на отслеживание (необязательно)</span>
            <input className="input" type="url" dir="ltr" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://" />
          </label>
          {dirty && (
            <button type="submit" disabled={busy} className="min-h-11 rounded-full bg-surface px-4 text-[16px] font-medium ring-1 ring-line disabled:opacity-50 sm:col-span-2">
              Сохранить трек-номер
            </button>
          )}
        </form>
      )}
      {["in_transit", "delivered", "refused"].includes(d.status) && (
        <label className="flex min-h-11 cursor-pointer items-center justify-center gap-2 rounded-full bg-surface px-4 text-[16px] font-medium ring-1 ring-line">
          <input type="file" multiple accept="image/*,application/pdf" className="sr-only" disabled={busy}
            onChange={(e) => { const fs = Array.from(e.target.files ?? []); e.target.value = ""; if (fs.length) proof(fs); }} />
          Фото второго экземпляра или акт отказа
        </label>
      )}
      {error && <p role="alert" className="text-danger">{error}</p>}
      {(NEXT[d.status]?.length ?? 0) > 0 && (
        <div className="flex flex-wrap gap-2">
          {NEXT[d.status]!.map((s, i) => (
            <button key={s} type="button" disabled={busy} onClick={() => save({ status: s })}
              className={`min-h-11 flex-1 rounded-full px-4 text-[16px] disabled:opacity-50 ${i === 0 ? "bg-action font-semibold text-white hover:bg-action-hover" : "bg-surface font-medium ring-1 ring-line"}`}>
              {ACTION[s] ?? STATUS[s]}
            </button>
          ))}
        </div>
      )}
    </Card>
  );
}
