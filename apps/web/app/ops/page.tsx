"use client";

import { useCallback, useEffect, useState } from "react";
import { Alert, Button } from "@/components/ui";
import { api, ApiError, errorText } from "@/lib/api";
import type { Ticket } from "@/app/support/page";

// The operations centre is a staff tool: its interface is in Russian only.
type Me = { email: string | null; desks: ("lawyers" | "clients")[]; new: { lawyers?: number; clients?: number } };
type App = {
  id: number; created_at: string; full_name: string; kind: string; organization: string | null; license_number: string | null;
  city: string | null; specializations: string[] | null; contact: string; message: string | null; wants_expert: boolean;
  status: string; ecp_verified: boolean; ecp_name: string | null; note: string | null;
};
type OpsTicket = Ticket & { name: string | null; email: string | null; phone: string | null; language: string };
type Req = { id: number; case_id: string; lawyer_ref: string | null; full_name: string; phone: string; email: string | null; status: string; note: string | null; created_at: string };

const KIND: Record<string, string> = { advocate: "Адвокат", consultant: "Юридический консультант", ngo: "Правозащитная организация" };
const APP_STATUS: Record<string, string> = { new: "Новая", verified: "Подтверждена", rejected: "Отклонена" };
const TICKET_KIND: Record<string, string> = { question: "Вопрос", complaint: "Жалоба", suggestion: "Предложение" };
const TICKET_STATUS: Record<string, string> = { new: "Новое", in_progress: "В работе", done: "Решено" };
const REQ_STATUS: Record<string, string> = { new: "Новая", passed: "Передана юристу", closed: "Закрыта" };
type Pay = {
  id: number; code: string; amount: number; currency: string | null; status: string; method: string; case_id: string;
  case_title: string | null; client_email: string | null; client_phone: string | null; created_at: string;
  claimed_at: string | null; decided_at: string | null; decided_by: string | null; note: string | null;
};
const PAY_STATUS: Record<string, string> = {
  awaiting_confirmation: "Ждёт подтверждения", pending: "Не оплачен", not_found: "Не найдена", paid: "Оплачен",
};
const money = (n: number, cur: string | null) => `${n.toLocaleString("ru-RU")} ${cur === "KZT" ? "₸" : cur ?? ""}`;
const when = (iso: string) => new Date(iso).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });

/** Operations centre: the lawyers desk (applications) and the clients desk (questions, complaints, suggestions, requests,
 * document payments by transfer). */
export default function OpsPage() {
  const [me, setMe] = useState<Me | null>(null);
  const [desk, setDesk] = useState<"lawyers" | "clients">("lawyers");
  const loadMe = useCallback(() => api<Me>("/v1/ops/me").then((m) => {
    setMe(m);
    if (m.desks.length && !m.desks.includes(desk)) setDesk(m.desks[0]);
  }).catch(() => setMe({ email: null, desks: [], new: {} })), [desk]);
  useEffect(() => { loadMe(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  if (!me) return <p className="text-muted">Загружаем…</p>;
  if (!me.desks.length) {
    return (
      <div className="mx-auto max-w-md space-y-4">
        <h1 className="text-2xl font-semibold">Оперативный центр</h1>
        <p className="text-muted">
          {me.email ? <>Адрес <b>{me.email}</b> не подключён к оперативному центру. Войдите по e-mail оператора.</>
            : "Для работы войдите по e-mail оператора: на почту придёт код."}
        </p>
        <Button href="/account?next=/ops" icon="mail">Войти по e-mail</Button>
      </div>
    );
  }
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Оперативный центр</h1>
          <p className="text-sm text-muted">{me.email}</p>
        </div>
      </div>
      {me.desks.length > 1 && (
        <div role="tablist" className="flex gap-2">
          {me.desks.map((d) => (
            <button key={d} role="tab" aria-selected={desk === d} onClick={() => setDesk(d)}
              className={`min-h-11 rounded-full border px-4 text-sm font-semibold ${desk === d ? "border-brand bg-brand text-white" : "border-line bg-surface"}`}>
              {d === "lawyers" ? "Юристы и адвокаты" : "Клиенты"}
              {(me.new[d] ?? 0) > 0 && <span className="ms-2 rounded-full bg-white/25 px-2">{me.new[d]}</span>}
            </button>
          ))}
        </div>
      )}
      {desk === "lawyers" ? <LawyersDesk onChange={loadMe} /> : <ClientsDesk onChange={loadMe} />}
    </div>
  );
}

function Filter({ value, options, onChange }: { value: string; options: Record<string, string>; onChange: (v: string) => void }) {
  return (
    <div className="flex flex-wrap gap-2">
      {[["", "Все"], ...Object.entries(options)].map(([k, label]) => (
        <button key={k} onClick={() => onChange(k)}
          className={`min-h-10 rounded-full border px-3 text-sm ${value === k ? "border-brand bg-brand-50 font-semibold text-brand" : "border-line bg-surface"}`}>{label}</button>
      ))}
    </div>
  );
}

function Note({ value, onSave }: { value: string | null; onSave: (v: string) => Promise<void> }) {
  const [text, setText] = useState(value ?? "");
  const [saved, setSaved] = useState(false);
  return (
    <label className="block text-xs text-muted">Заметка оператора (видна только оперативному центру)
      <div className="mt-1 flex gap-2">
        <input className="input min-h-10 flex-1 text-sm text-ink" value={text} onChange={(e) => { setText(e.target.value); setSaved(false); }} />
        <button type="button" disabled={text === (value ?? "")} onClick={async () => { await onSave(text); setSaved(true); }}
          className="min-h-10 rounded-xl border border-line px-3 text-sm font-medium disabled:opacity-40">{saved ? "Сохранено" : "Сохранить"}</button>
      </div>
    </label>
  );
}

function LawyersDesk({ onChange }: { onChange: () => void }) {
  const [status, setStatus] = useState("new");
  const [rows, setRows] = useState<App[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => api<App[]>(`/v1/ops/lawyers/applications${status ? `?status=${status}` : ""}`)
    .then(setRows).catch((e) => setError(errorText(e))), [status]);
  useEffect(() => { load(); }, [load]);

  async function update(id: number, body: { status?: string; note?: string }) {
    setError(null);
    try {
      await api(`/v1/ops/lawyers/applications/${id}`, { method: "POST", body: JSON.stringify(body) });
      if (body.status) { load(); onChange(); }
    } catch (e) {
      setError(e instanceof ApiError && e.code === "ecp_required"
        ? "Подтвердить можно только после входа юриста по ЭЦП: ФИО и ИИН известны только из сертификата. Попросите юриста войти по ЭЦП в кабинете юриста."
        : errorText(e));
    }
  }

  return (
    <section className="space-y-4">
      <h2 className="text-lg font-semibold">Заявки юристов, адвокатов и правозащитных организаций</h2>
      <Filter value={status} options={APP_STATUS} onChange={setStatus} />
      {error && <Alert tone="danger" role="alert">{error}</Alert>}
      {rows && rows.length === 0 && <p className="text-muted">Заявок нет.</p>}
      {rows?.map((a) => (
        <article key={a.id} className="card space-y-3 text-sm">
          <p className="flex flex-wrap items-center gap-2">
            <b className="text-base">№{a.id} · {a.full_name}</b>
            <span className="chip">{APP_STATUS[a.status] ?? a.status}</span>
            <span className={`chip ${a.ecp_verified ? "text-brand" : "text-warning"}`}>{a.ecp_verified ? `ЭЦП: ${a.ecp_name ?? "подтверждена"}` : "ЭЦП ещё нет"}</span>
            <span className="text-xs text-muted">{when(a.created_at)}</span>
          </p>
          <dl className="grid gap-x-4 gap-y-1 sm:grid-cols-[max-content_1fr]">
            <dt className="text-muted">Статус</dt><dd>{KIND[a.kind] ?? a.kind}{a.organization ? ` · ${a.organization}` : ""}</dd>
            {a.license_number && <><dt className="text-muted">Лицензия / членство</dt><dd>{a.license_number}</dd></>}
            {a.city && <><dt className="text-muted">Город</dt><dd>{a.city}</dd></>}
            {!!a.specializations?.length && <><dt className="text-muted">Специализации</dt><dd>{a.specializations.join(", ")}</dd></>}
            <dt className="text-muted">Контакт</dt><dd><a className="link" href={a.contact.includes("@") ? `mailto:${a.contact}` : `tel:${a.contact.replace(/[^\d+]/g, "")}`}>{a.contact}</a></dd>
            {a.wants_expert && <><dt className="text-muted">Эксперт</dt><dd>Готов проверять сценарии</dd></>}
          </dl>
          {a.message && <p className="whitespace-pre-line rounded-xl bg-sand px-3 py-2">{a.message}</p>}
          <Note value={a.note} onSave={(note) => update(a.id, { note })} />
          <div className="flex flex-wrap gap-2">
            {a.status !== "verified" && (
              <Button icon="check" disabled={!a.ecp_verified} onClick={() => update(a.id, { status: "verified" })}
                title={a.ecp_verified ? undefined : "Нужен вход юриста по ЭЦП"}>Подтвердить и открыть доступ</Button>
            )}
            {a.status !== "rejected" && <Button variant="secondary" onClick={() => update(a.id, { status: "rejected" })}>Отклонить</Button>}
            {a.status !== "new" && <Button variant="secondary" onClick={() => update(a.id, { status: "new" })}>Вернуть в новые</Button>}
          </div>
          {!a.ecp_verified && a.status === "new" && (
            <p className="text-xs text-muted">Подтверждение станет доступно, когда юрист войдёт по ЭЦП в кабинете юриста — ему приходит эта подсказка на экране заявки.</p>
          )}
        </article>
      ))}
    </section>
  );
}

function ClientsDesk({ onChange }: { onChange: () => void }) {
  const [tab, setTab] = useState<"tickets" | "requests" | "payments">("tickets");
  return (
    <section className="space-y-4">
      <div className="flex gap-2">
        {([["tickets", "Вопросы, жалобы, предложения"], ["requests", "Заявки юристу"], ["payments", "Оплаты документов"]] as const).map(([k, label]) => (
          <button key={k} onClick={() => setTab(k)}
            className={`min-h-10 rounded-full border px-3 text-sm ${tab === k ? "border-brand bg-brand-50 font-semibold text-brand" : "border-line bg-surface"}`}>{label}</button>
        ))}
      </div>
      {tab === "tickets" ? <Tickets onChange={onChange} /> : tab === "requests" ? <Requests onChange={onChange} /> : <Payments onChange={onChange} />}
    </section>
  );
}

function Tickets({ onChange }: { onChange: () => void }) {
  const [status, setStatus] = useState("new");
  const [rows, setRows] = useState<OpsTicket[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => api<OpsTicket[]>(`/v1/ops/clients/tickets${status ? `?status=${status}` : ""}`)
    .then(setRows).catch((e) => setError(errorText(e))), [status]);
  useEffect(() => { load(); }, [load]);
  const post = async (path: string, body: object) => {
    setError(null);
    try { await api(path, { method: "POST", body: JSON.stringify(body) }); load(); onChange(); return true; }
    catch (e) { setError(errorText(e)); return false; }
  };
  return (
    <>
      <Filter value={status} options={TICKET_STATUS} onChange={setStatus} />
      {error && <Alert tone="danger" role="alert">{error}</Alert>}
      {rows && rows.length === 0 && <p className="text-muted">Обращений нет.</p>}
      {rows?.map((tk) => <TicketCard key={tk.id} tk={tk} post={post} />)}
    </>
  );
}

function TicketCard({ tk, post }: { tk: OpsTicket; post: (path: string, body: object) => Promise<boolean> }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <article className="card space-y-3 text-sm">
      <p className="flex flex-wrap items-center gap-2">
        <b className="text-base">{TICKET_KIND[tk.kind] ?? tk.kind} №{tk.id}</b>
        <span className="chip">{TICKET_STATUS[tk.status] ?? tk.status}</span>
        <span className="text-xs text-muted">{when(tk.created_at)} · язык: {tk.language}</span>
      </p>
      <p>
        {tk.name ?? "Без имени"}
        {tk.email && <> · <a className="link" href={`mailto:${tk.email}`}>{tk.email}</a></>}
        {tk.phone && <> · <a className="link" href={`tel:${tk.phone.replace(/[^\d+]/g, "")}`}>{tk.phone}</a></>}
        {tk.case_id && <span className="text-muted"> · дело {tk.case_id.slice(0, 8)}</span>}
      </p>
      {tk.messages.map((m) => (
        <div key={m.id} className={`rounded-2xl px-3 py-2 ${m.author === "desk" ? "ms-6 bg-brand-50" : "me-6 bg-sand"}`}>
          <p className="text-xs font-semibold text-muted">{m.author === "desk" ? "Оперативный центр" : "Клиент"} · {when(m.created_at)}</p>
          <p className="whitespace-pre-line">{m.text}</p>
        </div>
      ))}
      <label className="block text-xs text-muted">Ответ клиенту (придёт на e-mail и появится на странице «Написать нам»)
        <textarea className="input mt-1 min-h-24 text-sm text-ink" value={text} onChange={(e) => setText(e.target.value)} />
      </label>
      <div className="flex flex-wrap gap-2">
        <Button icon={busy ? "spinner" : "send"} disabled={busy || !text.trim()}
          onClick={async () => { setBusy(true); if (await post(`/v1/ops/clients/tickets/${tk.id}/reply`, { text })) setText(""); setBusy(false); }}>Отправить ответ</Button>
        {tk.status !== "done" && <Button variant="secondary" icon="check" onClick={() => post(`/v1/ops/clients/tickets/${tk.id}/status`, { status: "done" })}>Отметить решённым</Button>}
        {tk.status === "done" && <Button variant="secondary" onClick={() => post(`/v1/ops/clients/tickets/${tk.id}/status`, { status: "in_progress" })}>Вернуть в работу</Button>}
      </div>
    </article>
  );
}

function Requests({ onChange }: { onChange: () => void }) {
  const [status, setStatus] = useState("new");
  const [rows, setRows] = useState<Req[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => api<Req[]>(`/v1/ops/clients/lawyer-requests${status ? `?status=${status}` : ""}`)
    .then(setRows).catch((e) => setError(errorText(e))), [status]);
  useEffect(() => { load(); }, [load]);
  async function update(id: number, body: { status?: string; note?: string }) {
    setError(null);
    try { await api(`/v1/ops/clients/lawyer-requests/${id}`, { method: "POST", body: JSON.stringify(body) }); if (body.status) { load(); onChange(); } }
    catch (e) { setError(errorText(e)); }
  }
  return (
    <>
      <Filter value={status} options={REQ_STATUS} onChange={setStatus} />
      {error && <Alert tone="danger" role="alert">{error}</Alert>}
      {rows && rows.length === 0 && <p className="text-muted">Заявок нет.</p>}
      {rows?.map((r) => (
        <article key={r.id} className="card space-y-3 text-sm">
          <p className="flex flex-wrap items-center gap-2">
            <b className="text-base">Заявка юристу №{r.id} · {r.full_name}</b>
            <span className="chip">{REQ_STATUS[r.status] ?? r.status}</span>
            <span className="text-xs text-muted">{when(r.created_at)}</span>
          </p>
          <p>
            <a className="link" href={`tel:${r.phone.replace(/[^\d+]/g, "")}`}>{r.phone}</a>
            {r.email && <> · <a className="link" href={`mailto:${r.email}`}>{r.email}</a></>}
            {r.lawyer_ref && <span className="text-muted"> · выбран юрист: {r.lawyer_ref}</span>}
          </p>
          <p className="text-muted">Дело: <span dir="ltr" className="font-mono">{r.case_id}</span></p>
          <Note value={r.note} onSave={(note) => update(r.id, { note })} />
          <div className="flex flex-wrap gap-2">
            {r.status !== "passed" && <Button icon="check" onClick={() => update(r.id, { status: "passed" })}>Передана юристу</Button>}
            {r.status !== "closed" && <Button variant="secondary" onClick={() => update(r.id, { status: "closed" })}>Закрыть</Button>}
            {r.status !== "new" && <Button variant="secondary" onClick={() => update(r.id, { status: "new" })}>Вернуть в новые</Button>}
          </div>
        </article>
      ))}
    </>
  );
}

/** Document payments by transfer: the client pressed «Я оплатил(а)»; find the transfer in Kaspi by the code in its comment. */
function Payments({ onChange }: { onChange: () => void }) {
  const [status, setStatus] = useState("awaiting_confirmation");
  const [rows, setRows] = useState<Pay[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<number | null>(null);
  const load = useCallback(() => api<Pay[]>(`/v1/ops/clients/payments?status=${status}`)
    .then(setRows).catch((e) => setError(errorText(e))), [status]);
  useEffect(() => { load(); }, [load]);
  async function decide(id: number, decision: "paid" | "not_found", note?: string) {
    setError(null);
    setBusy(id);
    try {
      await api(`/v1/ops/clients/payments/${id}`, { method: "POST", body: JSON.stringify({ decision, note }) });
      load(); onChange();
    } catch (e) {
      setError(e instanceof ApiError && e.code === "already_paid" ? "Этот счёт уже отмечен оплаченным." : errorText(e));
    } finally { setBusy(null); }
  }
  return (
    <>
      <p className="text-sm text-muted">
        Клиент нажал «Я оплатил(а)». Найдите в Kaspi перевод на эту сумму с кодом в комментарии и отметьте результат —
        клиент получит уведомление. После «Оплата получена» документ можно подготовить и скачать.
      </p>
      <div className="flex flex-wrap gap-2">
        {Object.entries(PAY_STATUS).map(([k, label]) => (
          <button key={k} onClick={() => setStatus(k)}
            className={`min-h-10 rounded-full border px-3 text-sm ${status === k ? "border-brand bg-brand-50 font-semibold text-brand" : "border-line bg-surface"}`}>{label}</button>
        ))}
      </div>
      {error && <Alert tone="danger" role="alert">{error}</Alert>}
      {rows && rows.length === 0 && <p className="text-muted">Счетов нет.</p>}
      {rows?.map((p) => (
        <article key={p.id} className="card space-y-3 text-sm">
          <p className="flex flex-wrap items-center gap-2">
            <b className="text-base">Код <span dir="ltr" className="font-mono">{p.code}</span> · {money(p.amount, p.currency)}</b>
            <span className="chip">{PAY_STATUS[p.status] ?? p.status}</span>
            <span className="text-xs text-muted">счёт №{p.id} от {when(p.created_at)}{p.claimed_at ? ` · «оплатил(а)» ${when(p.claimed_at)}` : ""}</span>
          </p>
          <p>
            {p.case_title ?? "Дело"} <span className="text-muted">· <span dir="ltr" className="font-mono">{p.case_id.slice(0, 8)}</span></span>
            {p.client_email && <> · <a className="link" href={`mailto:${p.client_email}`}>{p.client_email}</a></>}
            {p.client_phone && <> · <a className="link" href={`tel:${p.client_phone.replace(/[^\d+]/g, "")}`}>{p.client_phone}</a></>}
          </p>
          {p.decided_at && <p className="text-xs text-muted">Решение: {when(p.decided_at)} · {p.decided_by}{p.note ? ` · ${p.note}` : ""}</p>}
          {p.status !== "paid" && (
            <div className="flex flex-wrap gap-2">
              <Button icon="check" disabled={busy === p.id} onClick={() => decide(p.id, "paid")}>Оплата получена</Button>
              {p.status !== "not_found" && (
                <Button variant="secondary" disabled={busy === p.id} onClick={() => decide(p.id, "not_found")}>Не найдена</Button>
              )}
            </div>
          )}
        </article>
      ))}
    </>
  );
}
