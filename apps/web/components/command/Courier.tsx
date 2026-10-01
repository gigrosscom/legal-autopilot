"use client";

import { useCallback, useEffect, useState } from "react";
import { adminApi, ApiError, errorText } from "@/lib/api";
import { Card, H2, Loading, useCentre } from "./ui";

type Item = {
  id: string; status: string; provider: string; provider_label: string; case_id: string; client: string | null;
  pickup_address: string; pickup_date: string; pickup_from: string; pickup_to: string; contact_name: string;
  contact_phone: string; recipient_name: string; recipient_address: string; recipient_phone: string | null;
  price: number; currency: string | null; tracking: string | null; external_id: string | null; error: string | null;
  attempts: number; signer_name: string | null; comment: string | null; invoice_code: string | null;
  invoice_status: string | null; meta: { cost?: string; intake_error?: string };
};
type List = { provider: string; has_api: boolean; webhook: boolean; items: Item[] };

const STATUS: Record<string, string> = {
  awaiting_payment: "ждёт оплаты", paid: "оплачено — закажите курьера", ordered: "курьер заказан", picked_up: "забрал",
  in_transit: "в пути", delivered: "вручено", refused: "отказ получателя", returned: "второй экземпляр у клиента",
  cancelled: "отменено",
};
const NEXT: Record<string, string[]> = {
  paid: ["ordered", "cancelled"], ordered: ["picked_up", "in_transit", "delivered", "refused", "cancelled"],
  picked_up: ["in_transit", "delivered", "refused"], in_transit: ["delivered", "refused"],
  delivered: ["returned"], refused: ["returned"],
};
const LABEL: Record<string, string> = {
  ordered: "Заказан", picked_up: "Забрал", in_transit: "В пути", delivered: "Вручено", refused: "Отказ",
  returned: "Экземпляр вернули", cancelled: "Отменить",
};
const day = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit" });

/** «Курьер» (pilot): deliveries on their way. With no courier API (manual) the duty operator orders the courier,
 *  enters the tracking number and moves the status; the client sees every step in the case. */
export function CourierDesk() {
  const { token } = useCentre();
  const [list, setList] = useState<List | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => adminApi<List>("/v1/admin/courier", token)
    .then((r) => { setList(r); setError(null); }).catch((e) => setError(errorText(e))), [token]);
  useEffect(() => { load(); }, [load]);
  if (list && list.items.length === 0 && !error) {
    return (
      <section className="space-y-2">
        <H2 count={0}>Курьер</H2>
        <p className="text-muted">Нет доставок в работе. Служба: {list.provider === "manual" ? "вручную (без API)" : list.provider}.</p>
      </section>
    );
  }
  return (
    <section className="space-y-3">
      <H2 count={list?.items.length}>Курьер</H2>
      {error && <p role="alert" className="text-danger">{error}</p>}
      {!list && !error && <Loading />}
      {list && (
        <p className="text-[15px] text-muted">
          Служба: {list.provider === "manual" ? "вручную — закажите курьера и внесите номер и статусы" : `${list.provider} (API${list.webhook ? ", вебхук" : ", опрос"})`}.
          Вручено → срок ответа клиенту идёт с даты вручения.
        </p>
      )}
      <ul className="space-y-3">
        {list?.items.map((d) => <Row key={d.id} d={d} onDone={load} />)}
      </ul>
    </section>
  );
}

function Row({ d, onDone }: { d: Item; onDone: () => void }) {
  const { token } = useCentre();
  const [tracking, setTracking] = useState(d.tracking ?? "");
  const [signer, setSigner] = useState(d.signer_name ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function send(body: Record<string, unknown>, path = "") {
    setBusy(true); setError(null);
    try {
      await adminApi(`/v1/admin/courier/${d.id}${path}`, token, { method: "POST", body: JSON.stringify(body) });
      onDone();
    } catch (e) {
      setError(e instanceof ApiError && e.code === "status_not_forward" ? "Статус уже дальше." : errorText(e));
    } finally { setBusy(false); }
  }

  return (
    <Card as="li" className="space-y-2">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-[17px] font-semibold">{STATUS[d.status] ?? d.status}</p>
        <p className="text-[15px] tabular-nums text-muted">{day(d.pickup_date)} {d.pickup_from}–{d.pickup_to} · {d.price.toLocaleString("ru-RU")} ₸</p>
      </div>
      <p className="text-[15px]"><b>Забрать:</b> {d.pickup_address} · {d.contact_name}, <a className="underline" href={`tel:${d.contact_phone}`}>{d.contact_phone}</a></p>
      <p className="text-[15px]"><b>Вручить под подпись:</b> {d.recipient_name}, {d.recipient_address}{d.recipient_phone ? `, ${d.recipient_phone}` : ""}</p>
      {d.comment && <p className="text-[15px] text-muted">Комментарий: {d.comment}</p>}
      <p className="text-[14px] text-muted">
        Дело <a className="underline" href={`/case/${d.case_id}`}>{d.case_id.slice(0, 8)}</a>
        {d.client ? ` · ${d.client}` : ""}{d.invoice_code ? ` · счёт ${d.invoice_code} (${d.invoice_status})` : ""}
        {d.external_id ? ` · заказ ${d.provider_label} ${d.external_id}` : ""}{d.meta.cost ? ` · стоимость службы ${d.meta.cost}` : ""}
      </p>
      {(d.error || d.meta.intake_error) && (
        <p className="text-[15px] text-danger">Ошибка службы: {d.error ?? d.meta.intake_error}{d.attempts ? ` (попыток: ${d.attempts})` : ""}</p>
      )}
      {d.status !== "awaiting_payment" && (
        <div className="grid gap-2 sm:grid-cols-2">
          <input className="input min-h-11" placeholder="Номер отслеживания" value={tracking} onChange={(e) => setTracking(e.target.value)} />
          <input className="input min-h-11" placeholder="Кто расписался (ФИО, должность)" value={signer} onChange={(e) => setSigner(e.target.value)} />
        </div>
      )}
      <div className="flex flex-wrap gap-2">
        {(NEXT[d.status] ?? []).map((s) => (
          <button key={s} type="button" disabled={busy}
            onClick={() => {
              if (s === "cancelled" && !confirm("Отменить доставку? Деньги клиенту вернуть вручную.")) return;
              send({ status: s, tracking: tracking || null, signer_name: s === "delivered" ? signer || null : null });
            }}
            className={`min-h-11 rounded-full px-4 text-[15px] font-semibold disabled:opacity-50 ${s === "cancelled" ? "bg-surface ring-1 ring-line" : "bg-action text-white hover:bg-action-hover"}`}>
            {LABEL[s]}
          </button>
        ))}
        {d.status !== "awaiting_payment" && tracking !== (d.tracking ?? "") && (
          <button type="button" disabled={busy} onClick={() => send({ tracking })}
            className="min-h-11 rounded-full bg-surface px-4 text-[15px] ring-1 ring-line disabled:opacity-50">Сохранить номер</button>
        )}
        {d.provider !== "manual" && (
          <button type="button" disabled={busy} onClick={() => send({}, "/refresh")}
            className="min-h-11 rounded-full bg-surface px-4 text-[15px] ring-1 ring-line disabled:opacity-50">
            {d.status === "paid" ? "Повторить заказ" : "Обновить статус"}
          </button>
        )}
      </div>
      {error && <p role="alert" className="text-danger">{error}</p>}
    </Card>
  );
}
