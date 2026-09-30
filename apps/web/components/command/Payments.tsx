"use client";

import { useCallback, useEffect, useState } from "react";
import { adminApi, ApiError, errorText } from "@/lib/api";
import { Card, H2, Loading, useCentre } from "./ui";

type Pay = {
  id: number; code: string; amount: number; currency: string | null; status: string; purpose: string | null;
  case_title: string | null; client_email: string | null; client_phone: string | null; created_at: string;
  claimed_at: string | null;
  lawyer: { name: string | null; commission_pct: number | null; commission_amount: number | null; payout: number } | null;
};
const PURPOSE: Record<string, string> = { document: "один документ", case: "дело под ключ", lawyer: "работа юриста, на счёт ТОО" };
const sum = (n: number | null, currency: string | null) => `${(n ?? 0).toLocaleString("ru-RU")} ${currency === "KZT" ? "₸" : currency ?? ""}`;
const when = (iso: string) => new Date(iso).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });

/** Transfers the clients pressed «Оплатил(а)» for: find the code in the Kaspi comment and confirm. */
export function PaymentsToConfirm({ compact = false }: { compact?: boolean }) {
  const { token, reload } = useCentre();
  const [rows, setRows] = useState<Pay[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<number | null>(null);
  const load = useCallback(() => adminApi<Pay[]>("/v1/admin/payments?status=awaiting_confirmation", token)
    .then((r) => { setRows(r); setError(null); }).catch((e) => setError(errorText(e))), [token]);
  useEffect(() => { load(); }, [load]);

  async function decide(id: number, decision: "paid" | "not_found") {
    setBusy(id);
    setError(null);
    try {
      await adminApi(`/v1/admin/payments/${id}`, token, { method: "POST", body: JSON.stringify({ decision }) });
      await load();
      reload();
    } catch (e) {
      setError(e instanceof ApiError && e.code === "already_paid" ? "Этот счёт уже отмечен оплаченным." : errorText(e));
    } finally { setBusy(null); }
  }

  return (
    <section className="space-y-3">
      <H2 count={rows?.length}>Оплаты ждут подтверждения</H2>
      {error && <p role="alert" className="text-danger">{error}</p>}
      {!rows && !error && <Loading />}
      {rows?.length === 0 && <p className="text-muted">Нет оплат, ждущих подтверждения.</p>}
      {!compact && rows && rows.length > 0 && (
        <p className="text-[15px] text-muted">Найдите в Kaspi перевод на эту сумму с кодом в комментарии. Клиент получит письмо, документ готовится сразу.</p>
      )}
      <ul className="space-y-3">
        {rows?.map((p) => (
          <Card as="li" key={p.id} className="space-y-3">
            <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
              <p className="text-[20px] font-semibold tabular-nums">{p.amount.toLocaleString("ru-RU")} {p.currency === "KZT" ? "₸" : p.currency}</p>
              <p className="font-mono text-[17px]" dir="ltr">{p.code}</p>
            </div>
            <p className="text-[15px] text-muted">
              {p.case_title ?? "Дело"}{p.purpose && PURPOSE[p.purpose] ? ` · ${PURPOSE[p.purpose]}` : ""}
              {p.claimed_at ? ` · «оплатил(а)» ${when(p.claimed_at)}` : ` · счёт от ${when(p.created_at)}`}
              {p.client_phone ? ` · ${p.client_phone}` : p.client_email ? ` · ${p.client_email}` : ""}
            </p>
            {p.lawyer && (
              <p className="text-[15px]">
                Юрист: {p.lawyer.name ?? "—"} · комиссия {p.lawyer.commission_pct ?? 0} % = {sum(p.lawyer.commission_amount, p.currency)} · к выплате юристу {sum(p.lawyer.payout, p.currency)}
              </p>
            )}
            <div className="flex gap-2">
              <button type="button" disabled={busy === p.id} onClick={() => decide(p.id, "paid")}
                className="min-h-11 flex-1 rounded-full bg-action px-4 text-[16px] font-semibold text-white hover:bg-action-hover disabled:opacity-50">Оплата получена</button>
              <button type="button" disabled={busy === p.id} onClick={() => decide(p.id, "not_found")}
                className="min-h-11 rounded-full bg-surface px-4 text-[16px] font-medium ring-1 ring-line disabled:opacity-50">Не найдена</button>
            </div>
          </Card>
        ))}
      </ul>
    </section>
  );
}
