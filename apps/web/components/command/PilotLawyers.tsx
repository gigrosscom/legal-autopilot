"use client";

import { useCallback, useEffect, useState } from "react";
import { adminApi, errorText } from "@/lib/api";
import { Card, H2, Loading, useCentre } from "./ui";

type Row = {
  id: number; full_name: string; ecp_name: string | null; kind: string; organization: string | null; city: string | null;
  pilot: boolean; price: number | null; price_note: string; listed: boolean; has_account: boolean;
  requests: Record<"new" | "accepted" | "declined" | "paid", number>;
};
type State = { lawyers: Row[]; commission_pct: number; payment_available: boolean; payment_channel: string[] };
const KIND: Record<string, string> = { advocate: "адвокат", legal_consultant: "юридический консультант", human_rights: "правозащитник", other: "юрист" };

/** «Юрист по кнопке»: which verified lawyers take part in the closed pilot and at what price. */
export function PilotLawyers() {
  const { token } = useCentre();
  const [s, setS] = useState<State | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => adminApi<State>("/v1/admin/pilot-lawyers", token)
    .then((r) => { setS(r); setError(null); }).catch((e) => setError(errorText(e))), [token]);
  useEffect(() => { load(); }, [load]);

  return (
    <section className="space-y-3">
      <H2 count={s?.lawyers.filter((l) => l.listed).length}>Юристы пилота</H2>
      {error && <p role="alert" className="text-danger">{error}</p>}
      {!s && !error && <Loading />}
      {s && (
        <p className="text-[15px] text-muted">
          Клиент видит юриста в деле, когда он в пилоте и у него есть цена. Комиссия платформы — {s.commission_pct} % с юриста.{" "}
          {s.payment_available
            ? `Оплата юристам открыта: ${s.payment_channel.map((c) => (c === "kaspi_pay_link" ? "ссылка Kaspi Pay ТОО" : "реквизиты ТОО")).join(" и ")}.`
            : "Оплата юристам закрыта: на сервере не задан счёт ТОО (PAYMENT_KASPI_PAY_LINK или LAWYER_PAYMENT_ACCOUNT)."}
        </p>
      )}
      {s?.lawyers.length === 0 && <p className="text-muted">Пока нет юристов, чей статус подтверждён.</p>}
      <ul className="space-y-3">
        {s?.lawyers.map((l) => <PilotRow key={l.id} row={l} token={token} onSaved={load} />)}
      </ul>
    </section>
  );
}

function PilotRow({ row, token, onSaved }: { row: Row; token: string; onSaved: () => void }) {
  const [price, setPrice] = useState(row.price != null ? String(row.price) : "");
  const [note, setNote] = useState(row.price_note);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save(pilot: boolean) {
    setBusy(true);
    setError(null);
    try {
      await adminApi(`/v1/admin/lawyer-applications/${row.id}/pilot`, token, { method: "POST",
        body: JSON.stringify({ pilot, price: price ? Number(price) : null, price_note: note }) });
      onSaved();
    } catch (e) { setError(errorText(e)); } finally { setBusy(false); }
  }

  const r = row.requests;
  return (
    <Card as="li" className="space-y-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-[17px] font-semibold">{row.ecp_name || row.full_name}</p>
        <label className="flex items-center gap-2 text-[15px]">
          <input type="checkbox" className="h-5 w-5" checked={row.pilot} disabled={busy} onChange={(e) => save(e.target.checked)} />
          В пилоте
        </label>
      </div>
      <p className="text-[15px] text-muted">
        {[KIND[row.kind] ?? row.kind, row.organization, row.city].filter(Boolean).join(" · ")}
        {row.has_account ? "" : " · нет входа через ЭЦП"}
        {` · запросы: новых ${r.new}, принято ${r.accepted}, отказов ${r.declined}, оплачено ${r.paid}`}
      </p>
      <div className="grid gap-2 sm:grid-cols-[10rem_1fr_auto]">
        <input className="min-h-11 rounded-xl bg-surface px-3 ring-1 ring-line" inputMode="numeric" placeholder="Цена, ₸" aria-label="Цена, ₸"
          value={price} onChange={(e) => setPrice(e.target.value.replace(/[^\d]/g, ""))} />
        <input className="min-h-11 rounded-xl bg-surface px-3 ring-1 ring-line" placeholder="Что входит в цену" aria-label="Что входит в цену"
          maxLength={300} value={note} onChange={(e) => setNote(e.target.value)} />
        <button type="button" disabled={busy} onClick={() => save(row.pilot)}
          className="min-h-11 rounded-full bg-action px-4 text-[16px] font-semibold text-white hover:bg-action-hover disabled:opacity-50">Сохранить</button>
      </div>
      {error && <p role="alert" className="text-danger">{error}</p>}
    </Card>
  );
}
