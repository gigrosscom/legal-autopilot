"use client";

import { useCallback, useEffect, useState } from "react";
import { adminApi, API_URL, errorText } from "@/lib/api";
import { Card, Chip, H2, Loading, useCentre } from "./ui";

type Review = {
  action_id: string; case_id: string; title: string; scenario_id: string | null; language: string;
  waiting_since: string | null; addressee: string | null; has_pdf: boolean;
};
const hoursSince = (iso: string | null) => (iso ? Math.floor((Date.now() - new Date(iso).getTime()) / 3_600_000) : 0);

/** Documents that wait for the owner's check (court documents and others the engine holds). The client was told
 * «обычно в течение 24 часов»; approving releases the document to the client, returning sends the note back. */
export function ReviewsToCheck({ compact = false }: { compact?: boolean }) {
  const { token, reload } = useCentre();
  const [rows, setRows] = useState<Review[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [text, setText] = useState<Record<string, string>>({});
  const [note, setNote] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(() => adminApi<Review[]>("/v1/admin/reviews", token)
    .then((r) => { setRows(r); setError(null); }).catch((e) => setError(errorText(e))), [token]);
  useEffect(() => { load(); }, [load]);

  async function show(id: string) {
    setOpen(open === id ? null : id);
    if (text[id]) return;
    try {
      const r = await adminApi<{ text: string }>(`/v1/admin/actions/${id}/preview`, token);
      setText((t) => ({ ...t, [id]: r.text }));
    } catch (e) { setError(errorText(e)); }
  }

  async function download(r: Review) {
    // the file needs the admin header, so it is fetched here and handed to the browser
    try {
      const fmt = r.has_pdf ? "pdf" : "docx";
      const res = await fetch(`${API_URL}/v1/admin/actions/${r.action_id}/document?format=${fmt}`, { headers: { "X-Admin-Token": token } });
      if (!res.ok) throw new Error(String(res.status));
      const url = URL.createObjectURL(await res.blob());
      const a = Object.assign(document.createElement("a"), { href: url, download: `${r.title}.${fmt}` });
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 10_000);
    } catch (e) { setError(errorText(e)); }
  }

  async function decide(id: string, approved: boolean) {
    if (!approved && !(note[id] ?? "").trim()) { setError("Напишите, что исправить: клиент увидит этот комментарий."); return; }
    setBusy(id);
    setError(null);
    try {
      await adminApi(`/v1/admin/actions/${id}/approval`, token, {
        method: "POST", body: JSON.stringify({ approved, reviewer: "owner", note: (note[id] ?? "").trim() || null }),
      });
      await load();
      reload();
    } catch (e) { setError(errorText(e)); } finally { setBusy(null); }
  }

  if (compact && rows?.length === 0) return null;
  return (
    <section className="space-y-3">
      <H2 count={rows?.length}>Документы на проверке</H2>
      {error && <p role="alert" className="text-danger">{error}</p>}
      {!rows && !error && <Loading />}
      {rows?.length === 0 && <p className="text-muted">Нет документов, ждущих проверки.</p>}
      {!compact && rows && rows.length > 0 && (
        <p className="text-[15px] text-muted">Клиенту обещано «обычно в течение 24 часов». «Одобрить» — документ сразу откроется клиенту; «Вернуть» — клиент получит ваш комментарий.</p>
      )}
      <ul className="space-y-3">
        {rows?.map((r) => {
          const h = hoursSince(r.waiting_since);
          return (
            <Card as="li" key={r.action_id} className="space-y-3">
              <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                <p className="text-[18px] font-semibold">{r.title}</p>
                <Chip tone={h >= 24 ? "warn" : "neutral"}>{h < 1 ? "меньше часа" : `${h} ч`} ждёт</Chip>
              </div>
              <p className="text-[15px] text-muted">
                {r.addressee ? `Кому: ${r.addressee} · ` : ""}язык {r.language} · дело {r.case_id.slice(0, 8)}
              </p>
              <div className="flex flex-wrap gap-2">
                <button type="button" onClick={() => show(r.action_id)} aria-expanded={open === r.action_id}
                  className="min-h-10 rounded-full bg-surface px-4 text-[15px] font-medium ring-1 ring-line">{open === r.action_id ? "Скрыть текст" : "Читать текст"}</button>
                <button type="button" onClick={() => download(r)}
                  className="min-h-10 rounded-full bg-surface px-4 text-[15px] font-medium ring-1 ring-line">Скачать {r.has_pdf ? "PDF" : "DOCX"}</button>
              </div>
              {open === r.action_id && (
                <pre className="max-h-96 overflow-auto rounded-xl bg-sand p-3 text-[14px] leading-relaxed whitespace-pre-wrap">{text[r.action_id] ?? "Загрузка…"}</pre>
              )}
              <textarea rows={2} placeholder="Комментарий клиенту (обязателен, если возвращаете)" value={note[r.action_id] ?? ""}
                onChange={(e) => setNote((n) => ({ ...n, [r.action_id]: e.target.value }))}
                className="w-full rounded-xl bg-surface p-3 text-[15px] ring-1 ring-line" />
              <div className="flex gap-2">
                <button type="button" disabled={busy === r.action_id} onClick={() => decide(r.action_id, true)}
                  className="min-h-11 flex-1 rounded-full bg-action px-4 text-[16px] font-semibold text-white hover:bg-action-hover disabled:opacity-50">Одобрить</button>
                <button type="button" disabled={busy === r.action_id} onClick={() => decide(r.action_id, false)}
                  className="min-h-11 rounded-full bg-surface px-4 text-[16px] font-medium ring-1 ring-line disabled:opacity-50">Вернуть</button>
              </div>
            </Card>
          );
        })}
      </ul>
    </section>
  );
}
