"use client";

import { useCallback, useEffect, useState } from "react";
import { adminApi, downloadFile, type CaseView } from "@/lib/api";
import { useT } from "@/lib/i18n";

type Row = {
  id: string;
  status: string;
  status_label: string;
  needs_review: boolean;
  scenario_id: string | null;
  channel: string;
  amount_at_stake: string | null;
  currency: string | null;
  created_at: string;
  confidence: number | null;
  pending_approval_action_ids: string[];
};

type Filter = "all" | "needs_review" | "pending";

export default function AdminPage() {
  const t = useT();
  const [token, setToken] = useState("");
  const [input, setInput] = useState("");
  const [filter, setFilter] = useState<Filter>("pending");
  const [rows, setRows] = useState<Row[]>([]);
  const [selected, setSelected] = useState<CaseView | null>(null);
  const [previews, setPreviews] = useState<Record<string, string>>({});
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  useEffect(() => {
    try {
      const saved = localStorage.getItem("konsilier.admin");
      if (saved) setToken(saved);
    } catch {}
  }, []);

  const load = useCallback(async () => {
    if (!token) return;
    setError(null);
    const qs = filter === "needs_review" ? "?needs_review=true" : filter === "pending" ? "?pending_approval=true" : "";
    try {
      setRows(await adminApi<Row[]>(`/v1/admin/cases${qs}`, token));
    } catch (e) {
      setError(String(e));
    }
  }, [token, filter]);

  useEffect(() => {
    load();
  }, [load]);

  async function open(id: string) {
    const view = await adminApi<CaseView>(`/v1/admin/cases/${id}`, token);
    setSelected(view);
    const texts: Record<string, string> = {};
    for (const a of view.actions.filter((x) => x.has_docx)) {
      texts[a.id] = (await adminApi<{ text: string }>(`/v1/admin/actions/${a.id}/preview`, token)).text;
    }
    setPreviews(texts);
  }

  async function approve(actionId: string, approved: boolean) {
    const view = await adminApi<CaseView>(`/v1/admin/actions/${actionId}/approval`, token, {
      method: "POST",
      body: JSON.stringify({ approved, note: note || null, reviewer: "lawyer" }),
    });
    setSelected(view);
    setNote("");
    load();
  }

  async function close(result: string) {
    const view = await adminApi<CaseView>(`/v1/admin/cases/${selected!.id}/close`, token, {
      method: "POST",
      body: JSON.stringify({ result }),
    });
    setSelected(view);
    load();
  }

  if (!token) {
    return (
      <form
        className="card mx-auto max-w-sm space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          localStorage.setItem("konsilier.admin", input);
          setToken(input);
        }}
      >
        <h1 className="text-xl font-bold">{t("admin.title")}</h1>
        <input className="input" type="password" placeholder={t("admin.token")} value={input} onChange={(e) => setInput(e.target.value)} />
        <button className="btn-primary">{t("admin.save")}</button>
      </form>
    );
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[380px_1fr]">
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-bold">{t("admin.title")}</h1>
          <button
            className="text-xs text-ink/50 hover:text-brand"
            onClick={async () => setInfo(`sent: ${(await adminApi<{ sent: number }>("/v1/admin/scheduler/tick", token, { method: "POST" })).sent}`)}
          >
            {t("admin.tick")}
          </button>
        </div>
        <div className="flex gap-1 text-sm">
          {(["pending", "needs_review", "all"] as Filter[]).map((f) => (
            <button key={f} onClick={() => setFilter(f)} className={`rounded-lg px-3 py-1.5 ${filter === f ? "bg-ink text-white" : "bg-white"}`}>
              {f === "pending" ? t("admin.pendingApproval") : f === "needs_review" ? t("admin.needsReview") : t("admin.all")}
            </button>
          ))}
        </div>
        {info && <p className="text-xs text-ink/60">{info}</p>}
        {error && <p className="text-sm text-red-600">{error}</p>}
        <div className="space-y-2">
          {rows.map((r) => (
            <button key={r.id} onClick={() => open(r.id)} className={`card block w-full text-left text-sm hover:border-brand ${selected?.id === r.id ? "border-brand" : ""}`}>
              <div className="flex items-center justify-between gap-2">
                <span className="font-mono text-xs">{r.id.slice(0, 8)}</span>
                <span className="chip">{r.status_label}</span>
              </div>
              <div className="mt-1">{r.scenario_id ?? "— не квалифицировано —"}</div>
              <div className="mt-1 flex flex-wrap gap-1 text-xs">
                {r.needs_review && <span className="chip bg-amber-100">needs_review</span>}
                {r.pending_approval_action_ids.length > 0 && <span className="chip bg-brand/10">ждёт одобрения</span>}
                <span className="chip">{r.channel}</span>
                {r.amount_at_stake && <span className="chip">{r.amount_at_stake} {r.currency}</span>}
              </div>
            </button>
          ))}
        </div>
      </div>

      {selected && (
        <div className="space-y-4">
          <div className="card space-y-2 text-sm">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold">{selected.scenario?.title ?? "—"}</h2>
              <span className="chip">{selected.status_label}</span>
            </div>
            <p className="text-ink/60">
              confidence: {selected.qualification_confidence?.toFixed(2) ?? "—"} · {selected.scenario?.id}@{selected.scenario?.version}
            </p>
            <p className="whitespace-pre-line rounded-lg bg-ink/5 p-2">{selected.initial_text}</p>
            <dl className="grid grid-cols-2 gap-x-4 gap-y-1">
              {selected.facts.map((f) => (
                <div key={f.field}>
                  <dt className="text-xs text-ink/50">{f.label}</dt>
                  <dd>{f.value}</dd>
                </div>
              ))}
            </dl>
          </div>

          {selected.actions.map((a) => (
            <div key={a.id} className="card space-y-2 text-sm">
              <div className="flex items-center justify-between">
                <h3 className="font-semibold">{a.sequence}. {a.title}</h3>
                <span className="chip">{a.approval_status}</span>
              </div>
              {previews[a.id] && (
                <details open={a.approval_status === "pending"}>
                  <summary className="cursor-pointer text-ink/60">{t("admin.preview")}</summary>
                  <pre className="mt-2 max-h-96 overflow-auto whitespace-pre-wrap rounded-lg bg-ink/5 p-3 font-sans text-xs">{previews[a.id]}</pre>
                </details>
              )}
              {a.has_docx && (
                <div className="flex gap-2">
                  {a.has_pdf && (
                    <button className="btn-ghost" onClick={() => downloadFile(`/v1/admin/actions/${a.id}/document?format=pdf`, `${a.action_id}.pdf`, { "X-Admin-Token": token })}>⬇ PDF</button>
                  )}
                  <button className="btn-ghost" onClick={() => downloadFile(`/v1/admin/actions/${a.id}/document?format=docx`, `${a.action_id}.docx`, { "X-Admin-Token": token })}>⬇ DOCX</button>
                </div>
              )}
              {a.approval_status === "pending" && (
                <div className="space-y-2">
                  <input className="input" placeholder={t("admin.note")} value={note} onChange={(e) => setNote(e.target.value)} />
                  <div className="flex gap-2">
                    <button className="btn-primary" onClick={() => approve(a.id, true)}>{t("admin.approve")}</button>
                    <button className="btn-ghost" onClick={() => approve(a.id, false)}>{t("admin.reject")}</button>
                  </div>
                </div>
              )}
            </div>
          ))}

          {selected.status === "handed_to_lawyer" && (
            <div className="card flex flex-wrap items-center gap-2 text-sm">
              <span className="font-semibold">{t("admin.closeCase")}:</span>
              {["won", "partial", "lost", "settled", "abandoned"].map((r) => (
                <button key={r} className="btn-ghost" onClick={() => close(r)}>{r}</button>
              ))}
            </div>
          )}

          <details className="card text-xs">
            <summary className="cursor-pointer font-semibold">{t("admin.audit")}</summary>
            <table className="mt-2 w-full">
              <tbody>
                {selected.audit?.map((l, i) => (
                  <tr key={i} className="border-t border-ink/5 align-top">
                    <td className="py-1 pr-2 text-ink/50">{new Date(l.at).toLocaleString("ru-RU")}</td>
                    <td className="pr-2">{l.actor}</td>
                    <td className="pr-2 font-medium">{l.event}</td>
                    <td className="pr-2">{l.from ? `${l.from} → ${l.to}` : ""}</td>
                    <td className="font-mono text-[10px] text-ink/60">{JSON.stringify(l.data)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
        </div>
      )}
    </div>
  );
}
