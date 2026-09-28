"use client";

import { MetricsTab } from "@/components/MetricsTab";
import { useCallback, useEffect, useState } from "react";
import { CaseBoard, type BoardCard } from "@/components/CaseBoard";
import { LevelBadge, type Level } from "@/components/LevelBadge";
import { Alert, Badge, Button, Icon } from "@/components/ui";
import { adminApi, downloadFile, errorText, type CaseView } from "@/lib/api";
import { useT } from "@/lib/i18n";

type Card = {
  id: string; status: string; status_label: string; stage: string; needs_review: boolean; scenario_id: string | null;
  title: string | null; coverage_level: string; display_level?: string; hold_reason: string | null; channel: string;
  amount_at_stake: string | null; currency: string | null; created_at: string; confidence: number | null;
  pending_approval_action_ids: string[]; route_reasons: string[];
  tasks: { id: string; action_id: string; status: string; approval_status: string }[];
};
type Tab = "metrics" | "board" | "queue" | "holds" | "forums" | "demand" | "errors" | "lawyers";

export default function AdminPage() {
  const t = useT();
  const [token, setToken] = useState("");
  const [input, setInput] = useState("");
  const [tab, setTab] = useState<Tab>("queue");
  const [board, setBoard] = useState<Card[]>([]);
  const [queue, setQueue] = useState<Card[]>([]);
  const [holds, setHolds] = useState<Card[]>([]);
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
    try {
      const b = await adminApi<{ columns: { id: string; cards: Card[] }[] }>("/v1/admin/board", token);
      setBoard(b.columns.flatMap((c) => c.cards));
      // review queue: universal-path documents first — they always need a lawyer's approval
      const pending = await adminApi<Card[]>("/v1/admin/cases?pending_approval=true", token);
      setQueue([...pending].sort((a, b) => Number(b.coverage_level === "universal") - Number(a.coverage_level === "universal")));
      setHolds(await adminApi<Card[]>("/v1/admin/cases?on_hold=true", token));
    } catch (e) {
      setError(errorText(e));
    }
  }, [token]);

  useEffect(() => { load(); }, [load]);

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
    setSelected(await adminApi<CaseView>(`/v1/admin/actions/${actionId}/approval`, token, {
      method: "POST", body: JSON.stringify({ approved, note: note || null, reviewer: "lawyer" }),
    }));
    setNote("");
    load();
  }

  async function release(id: string) {
    setSelected(await adminApi<CaseView>(`/v1/admin/cases/${id}/release`, token, { method: "POST" }));
    load();
  }

  async function close(result: string) {
    setSelected(await adminApi<CaseView>(`/v1/admin/cases/${selected!.id}/close`, token, {
      method: "POST", body: JSON.stringify({ result }),
    }));
    load();
  }

  if (!token) {
    return (
      <form className="card mx-auto max-w-sm space-y-3" onSubmit={(e) => {
        e.preventDefault();
        try { localStorage.setItem("konsilier.admin", input); } catch {}
        setToken(input);
      }}>
        <h1 className="text-xl font-semibold">{t("admin.title")}</h1>
        <label htmlFor="tok" className="sr-only">{t("admin.token")}</label>
        <input id="tok" className="input" type="password" placeholder={t("admin.token")} value={input} onChange={(e) => setInput(e.target.value)} />
        <Button>{t("admin.save")}</Button>
      </form>
    );
  }

  const list = (rows: Card[]) => (
    <ul className="space-y-2">
      {rows.length === 0 && <li className="text-sm text-muted">{t("board.empty")}</li>}
      {rows.map((r) => (
        <li key={r.id}>
          <button onClick={() => open(r.id)}
            className={`card block w-full space-y-1 text-start text-sm hover:border-brand ${selected?.id === r.id ? "border-brand" : ""}`}>
            <div className="flex flex-wrap items-center gap-1.5">
              <LevelBadge level={(r.display_level ?? r.coverage_level) as Level} />
              <Badge>{r.status_label}</Badge>
              {r.hold_reason && <Badge tone="warning" icon="alert">{r.hold_reason}</Badge>}
            </div>
            <p className="font-semibold">{r.title ?? t("case.untitled")}</p>
            <p className="font-mono text-xs text-muted">{r.id.slice(0, 8)} · {new Date(r.created_at).toLocaleDateString("ru-RU")}</p>
          </button>
        </li>
      ))}
    </ul>
  );

  const cards: BoardCard[] = board.map((r) => ({
    id: r.id, href: "#case", title: r.title ?? t("case.untitled"), stage: r.stage, level: r.display_level ?? r.coverage_level,
    date: new Date(r.created_at).toLocaleDateString("ru-RU"),
    attention: r.hold_reason ? t("board.attention.hold") : r.pending_approval_action_ids.length ? t("board.attention.approval") : null,
    tasks: r.tasks.map((x) => ({ label: `${x.action_id} · ${x.approval_status}`, done: ["submitted", "responded"].includes(x.status) })),
  }));

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">{t("admin.title")}</h1>
        <Button variant="secondary" icon="clock" onClick={async () =>
          setInfo(`sent: ${(await adminApi<{ sent: number }>("/v1/admin/scheduler/tick", token, { method: "POST" })).sent}`)}>
          {t("admin.tick")}
        </Button>
      </div>
      <div role="tablist" className="flex flex-wrap gap-1">
        {(["queue", "board", "holds", "lawyers", "metrics", "forums", "demand", "errors"] as Tab[]).map((x) => (
          <button key={x} role="tab" aria-selected={tab === x} onClick={() => setTab(x)}
            className={`min-h-10 rounded-xl px-3 text-sm font-medium ${tab === x ? "bg-ink text-white" : "bg-surface"}`}>
            {t(`admin.tabs.${x}`)}{x === "queue" && queue.length ? ` · ${queue.length}` : ""}{x === "holds" && holds.length ? ` · ${holds.length}` : ""}
          </button>
        ))}
      </div>
      {info && <p className="text-xs text-muted">{info}</p>}
      {error && <Alert tone="danger" role="alert">{error}</Alert>}

      {tab === "board" && (
        <CaseBoard cards={cards} onlyNonEmptyOnMobile={false} onOpen={open} />
      )}

      <div className={`grid gap-6 ${tab === "queue" || tab === "holds" ? "lg:grid-cols-[360px_1fr]" : ""}`}>
        {tab === "queue" && list(queue)}
        {tab === "holds" && list(holds)}
        {tab === "forums" && <ForumsTab token={token} />}
        {tab === "demand" && <DemandTab token={token} />}
        {tab === "errors" && <ErrorsTab token={token} />}
        {tab === "metrics" && <MetricsTab token={token} />}
        {tab === "lawyers" && <LawyersTab token={token} />}

        {selected && tab !== "forums" && tab !== "demand" && tab !== "errors" && tab !== "lawyers" && tab !== "metrics" && (
          <div id="case" className="space-y-4">
            <div className="card space-y-2 text-sm">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="me-auto text-lg font-semibold">{selected.scenario?.title ?? selected.coverage.dispute?.title ?? "—"}</h2>
                <LevelBadge level={selected.coverage.level} />
                <Badge>{selected.status_label}</Badge>
              </div>
              <p className="text-muted">confidence: {selected.qualification_confidence?.toFixed(2) ?? "—"} · {selected.scenario?.id}</p>
              {selected.coverage.forum && <p>{t("admin.forum")}: {selected.coverage.forum.name}</p>}
              {selected.safety.hold_reason && (
                <Alert tone="warning" title={`${t("admin.hold")}: ${selected.safety.hold_reason}`}
                  actions={<Button onClick={() => release(selected.id)}>{t("admin.release")}</Button>} />
              )}
              <p className="whitespace-pre-line rounded-lg bg-sand p-2">{selected.initial_text}</p>
              <dl className="grid grid-cols-2 gap-x-4 gap-y-1">
                {selected.facts.map((f) => (
                  <div key={f.field}><dt className="text-xs text-muted">{f.label}</dt><dd>{f.value}</dd></div>
                ))}
              </dl>
            </div>

            {selected.actions.map((a) => (
              <div key={a.id} className="card space-y-2 text-sm">
                <div className="flex items-center justify-between gap-2">
                  <h3 className="font-semibold">{a.sequence}. {a.title}</h3>
                  <Badge tone={a.approval_status === "pending" ? "warning" : "neutral"}>{a.approval_status}</Badge>
                </div>
                {previews[a.id] && (
                  <details open={a.approval_status === "pending"}>
                    <summary className="cursor-pointer text-muted">{t("admin.preview")}</summary>
                    <pre className="mt-2 max-h-96 overflow-auto whitespace-pre-wrap rounded-lg bg-sand p-3 font-sans text-xs">{previews[a.id]}</pre>
                  </details>
                )}
                {a.has_docx && (
                  <div className="flex gap-2">
                    {a.has_pdf && <Button variant="secondary" icon="download" onClick={() => downloadFile(`/v1/admin/actions/${a.id}/document?format=pdf`, `${a.action_id}.pdf`, { "X-Admin-Token": token })}>PDF</Button>}
                    <Button variant="secondary" icon="download" onClick={() => downloadFile(`/v1/admin/actions/${a.id}/document?format=docx`, `${a.action_id}.docx`, { "X-Admin-Token": token })}>DOCX</Button>
                  </div>
                )}
                {a.approval_status === "pending" && (
                  <div className="space-y-2">
                    <label htmlFor={`note-${a.id}`} className="sr-only">{t("admin.note")}</label>
                    <input id={`note-${a.id}`} className="input" placeholder={t("admin.note")} value={note} onChange={(e) => setNote(e.target.value)} />
                    <div className="flex gap-2">
                      <Button icon="check" onClick={() => approve(a.id, true)}>{t("admin.approve")}</Button>
                      <Button variant="secondary" onClick={() => approve(a.id, false)}>{t("admin.reject")}</Button>
                    </div>
                  </div>
                )}
              </div>
            ))}

            <AssignLawyer token={token} caseId={selected.id} />

            {selected.status === "handed_to_lawyer" && (
              <div className="card flex flex-wrap items-center gap-2 text-sm">
                <span className="font-semibold">{t("admin.closeCase")}:</span>
                {["won", "partial", "lost", "settled", "abandoned"].map((r) => (
                  <Button key={r} variant="secondary" onClick={() => close(r)}>{r}</Button>
                ))}
              </div>
            )}

            <details className="card text-xs">
              <summary className="cursor-pointer font-semibold">{t("admin.audit")}</summary>
              <div className="overflow-x-auto">
                <table className="mt-2 w-full">
                  <tbody>
                    {selected.audit?.map((l, i) => (
                      <tr key={i} className="border-t border-line align-top">
                        <td className="py-1 pe-2 text-muted">{new Date(l.at).toLocaleString("ru-RU")}</td>
                        <td className="pe-2">{l.actor}</td>
                        <td className="pe-2 font-medium">{l.event}</td>
                        <td className="pe-2">{l.from ? `${l.from} → ${l.to}` : ""}</td>
                        <td className="font-mono text-[10px] text-muted">{JSON.stringify(l.data)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          </div>
        )}
      </div>
    </div>
  );
}

type LawyerApp = { id: number; full_name: string; kind: string; organization: string | null; license_number: string | null;
  city: string | null; contact: string; status: string; ecp_verified: boolean; ecp_name: string | null; created_at: string };

function LawyersTab({ token }: { token: string }) {
  const t = useT();
  const [rows, setRows] = useState<LawyerApp[]>([]);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => {
    adminApi<LawyerApp[]>("/v1/admin/lawyer-applications", token).then(setRows).catch((e) => setError(errorText(e)));
  }, [token]);
  useEffect(() => { load(); }, [load]);
  const setStatus = async (id: number, status: string) => {
    setError(null);
    try {
      await adminApi(`/v1/admin/lawyer-applications/${id}/status`, token, { method: "POST", body: JSON.stringify({ status }) });
      load();
    } catch (e) { setError(errorText(e)); }
  };
  return (
    <div className="space-y-3 lg:col-span-2">
      <p className="text-sm text-muted">{t("admin.lawyers.lead")}</p>
      {error && <Alert tone="danger" role="alert">{error}</Alert>}
      {rows.map((r) => (
        <div key={r.id} className="card space-y-2 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <span className="me-auto font-semibold">{r.ecp_name ?? r.full_name}</span>
            {r.ecp_verified ? <Badge tone="brand" icon="shieldCheck">{t("admin.lawyers.ecp")}</Badge>
              : <Badge tone="warning">{t("admin.lawyers.noEcp")}</Badge>}
            <Badge>{r.status}</Badge>
          </div>
          <p className="text-muted">{r.kind} · {r.organization ?? "—"} · {t("admin.lawyers.license")}: {r.license_number ?? "—"} · {r.city ?? "—"} · {r.contact}</p>
          {r.ecp_name && r.ecp_name.toLowerCase() !== r.full_name.toLowerCase() && (
            <p className="text-warning">{t("admin.lawyers.nameDiffers", { name: r.full_name })}</p>
          )}
          <div className="flex flex-wrap gap-2">
            <Button icon="check" disabled={!r.ecp_verified || r.status === "verified"} onClick={() => setStatus(r.id, "verified")}>{t("admin.lawyers.verify")}</Button>
            <Button variant="secondary" disabled={r.status === "rejected"} onClick={() => setStatus(r.id, "rejected")}>{t("admin.reject")}</Button>
          </div>
        </div>
      ))}
    </div>
  );
}

function AssignLawyer({ token, caseId }: { token: string; caseId: string }) {
  const t = useT();
  const [apps, setApps] = useState<LawyerApp[]>([]);
  const [pick, setPick] = useState<string>("");
  const [msg, setMsg] = useState<string | null>(null);
  useEffect(() => {
    adminApi<LawyerApp[]>("/v1/admin/lawyer-applications", token)
      .then((r) => setApps(r.filter((a) => a.status === "verified" && a.ecp_verified))).catch(() => setApps([]));
  }, [token]);
  if (!apps.length) return null;
  const assign = async () => {
    setMsg(null);
    try {
      const r = await adminApi<{ lawyer: { name: string } }>(`/v1/admin/cases/${caseId}/assign`, token,
        { method: "POST", body: JSON.stringify({ application_id: Number(pick) }) });
      setMsg(t("admin.lawyers.assigned", { name: r.lawyer.name }));
    } catch (e) { setMsg(errorText(e)); }
  };
  return (
    <div className="card flex flex-wrap items-center gap-2 text-sm">
      <label className="flex flex-1 flex-wrap items-center gap-2">
        <span className="font-semibold">{t("admin.lawyers.assign")}:</span>
        <select className="input max-w-xs" value={pick} onChange={(e) => setPick(e.target.value)}>
          <option value="">—</option>
          {apps.map((a) => <option key={a.id} value={a.id}>{a.ecp_name ?? a.full_name}</option>)}
        </select>
      </label>
      <Button disabled={!pick} onClick={assign}>{t("admin.lawyers.assignButton")}</Button>
      {msg && <p className="w-full text-muted" role="status">{msg}</p>}
    </div>
  );
}

type ForumRecord = { id: string; type: string; name: Record<string, string>; legal_effect: string; verified_at: string | null;
  verified_by: string | null; appeals_to: string[] };

const FORUM_TYPES = ["court", "prosecutor", "police", "regulator", "ministry", "ombudsman", "local_authority",
  "arbitration", "mediation", "private_org"];

/** Registry (source of truth in git) + drafts. Drafts never go live: they are exported to a reviewed PR. */
function ForumsTab({ token }: { token: string }) {
  const t = useT();
  const [data, setData] = useState<{ registry: ForumRecord[]; drafts: { id: number; forum_id: string; status: string; note: string | null }[] } | null>(null);
  const [form, setForm] = useState({ id: "kz.", type: "regulator", nameRu: "", nameKk: "", branches: "", docType: "complaint",
    kind: "portal", url: "", effect: "binding", source: "", note: "" });
  const [msg, setMsg] = useState<string | null>(null);
  const load = useCallback(() => adminApi<typeof data>("/v1/admin/forums?country=KZ", token).then(setData), [token]);
  useEffect(() => { load(); }, [load]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setMsg(null);
    const data = {
      id: form.id, type: form.type, name: { ru: form.nameRu, kk: form.nameKk },
      accepts: [{ branches: form.branches.split(",").map((s) => s.trim()).filter(Boolean) }],
      document_types: [form.docType], submission: [{ kind: form.kind, ...(form.kind === "portal" ? { url: form.url } : {}) }],
      languages: ["ru", "kk"], legal_effect: form.effect, source: form.source || "TODO",
    };
    try {
      await adminApi("/v1/admin/forum-drafts", token, { method: "POST", body: JSON.stringify({ country: "KZ", data, note: form.note, author: "admin" }) });
      setMsg(t("admin.forums.saved"));
      load();
    } catch (err) {
      setMsg(errorText(err));
    }
  }

  const f = (k: keyof typeof form) => ({ value: form[k], onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setForm({ ...form, [k]: e.target.value }) });
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <div className="space-y-3">
        <h2 className="text-lg font-semibold">{t("admin.forums.registry")}</h2>
        <p className="text-sm text-muted">{t("admin.forums.registryLead")}</p>
        <ul className="space-y-2">
          {data?.registry.map((r) => (
            <li key={r.id} className="card space-y-1 p-3 text-sm">
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="font-mono text-xs">{r.id}</span>
                <Badge tone={r.verified_at ? "brand" : "neutral"} icon={r.verified_at ? "shieldCheck" : "hourglass"}>
                  {r.verified_at ? `${t("forum.verified")} · ${r.verified_by ?? ""}` : t("forum.unverified")}
                </Badge>
                <Badge>{r.legal_effect}</Badge>
              </div>
              <p>{r.name.ru}</p>
              {r.appeals_to.length > 0 && <p className="text-xs text-muted">→ {r.appeals_to.join(", ")}</p>}
            </li>
          ))}
        </ul>
      </div>
      <div className="space-y-4">
        <form onSubmit={submit} className="card space-y-3">
          <h2 className="text-lg font-semibold">{t("admin.forums.newDraft")}</h2>
          <Alert tone="info">{t("admin.forums.draftNote")}</Alert>
          <div className="grid gap-2 sm:grid-cols-2">
            <label className="text-xs text-muted">id<input className="input mt-1 font-mono" required {...f("id")} /></label>
            <label className="text-xs text-muted">type
              <select className="input mt-1" {...f("type")}>{FORUM_TYPES.map((x) => <option key={x}>{x}</option>)}</select></label>
            <label className="text-xs text-muted">name (ru)<input className="input mt-1" required {...f("nameRu")} /></label>
            <label className="text-xs text-muted">name (kk)<input className="input mt-1" required {...f("nameKk")} /></label>
            <label className="text-xs text-muted">branches<input className="input mt-1" placeholder="labor, family" required {...f("branches")} /></label>
            <label className="text-xs text-muted">document
              <select className="input mt-1" {...f("docType")}>{["complaint", "statement", "lawsuit", "appeal"].map((x) => <option key={x}>{x}</option>)}</select></label>
            <label className="text-xs text-muted">submission
              <select className="input mt-1" {...f("kind")}>{["portal", "email", "post", "in_person"].map((x) => <option key={x}>{x}</option>)}</select></label>
            <label className="text-xs text-muted">url<input className="input mt-1" {...f("url")} /></label>
            <label className="text-xs text-muted">legal_effect
              <select className="input mt-1" {...f("effect")}>{["binding", "advisory", "none"].map((x) => <option key={x}>{x}</option>)}</select></label>
            <label className="text-xs text-muted">source<input className="input mt-1" placeholder="TODO" {...f("source")} /></label>
          </div>
          <label className="block text-xs text-muted">{t("admin.note")}<input className="input mt-1" {...f("note")} /></label>
          <Button icon="plus">{t("admin.forums.save")}</Button>
          {msg && <p className="text-sm">{msg}</p>}
        </form>
        <div className="space-y-2">
          <h3 className="font-semibold">{t("admin.forums.drafts")}</h3>
          {data?.drafts.length === 0 && <p className="text-sm text-muted">{t("board.empty")}</p>}
          <ul className="space-y-1 text-sm">
            {data?.drafts.map((d) => (
              <li key={d.id} className="flex items-center gap-2"><Icon name="document" size={16} />
                <span className="font-mono text-xs">{d.forum_id}</span><Badge>{d.status}</Badge></li>
            ))}
          </ul>
          <p className="text-xs text-muted"><code>python -m konsilier.cli forums-export KZ drafts.yaml</code></p>
        </div>
      </div>
    </div>
  );
}

function DemandTab({ token }: { token: string }) {
  const t = useT();
  const [rows, setRows] = useState<{ country: string; branch: string | null; dispute_type: string | null; level: string; count: number }[]>([]);
  useEffect(() => { adminApi<typeof rows>("/v1/admin/demand", token).then(setRows); }, [token]);
  return (
    <div className="card space-y-3">
      <h2 className="text-lg font-semibold">{t("admin.demand.title")}</h2>
      <p className="text-sm text-muted">{t("admin.demand.lead")}</p>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead><tr className="text-start text-xs text-muted">
            <th className="py-1 pe-3 text-start">{t("admin.demand.country")}</th><th className="pe-3 text-start">{t("admin.demand.dispute")}</th>
            <th className="pe-3 text-start">{t("admin.demand.level")}</th><th className="text-end">{t("admin.demand.count")}</th></tr></thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} className="border-t border-line">
                <td className="py-1.5 pe-3">{r.country}</td><td className="pe-3 font-mono text-xs">{r.dispute_type ?? "—"}</td>
                <td className="pe-3">{r.level}</td><td className="text-end tabular-nums">{r.count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

type ClientError = { at: string; message: string; stack?: string | null; url?: string | null; user_agent?: string | null; translated?: boolean | null };

/** Browser crash reports sent by the web app (lib/report.ts), newest first. */
function ErrorsTab({ token }: { token: string }) {
  const t = useT();
  const [rows, setRows] = useState<ClientError[] | null>(null);
  useEffect(() => { adminApi<ClientError[]>("/v1/admin/client-errors", token).then(setRows).catch(() => setRows([])); }, [token]);
  return (
    <div className="card space-y-3">
      <h2 className="text-lg font-semibold">{t("admin.tabs.errors")}</h2>
      {rows?.length === 0 && <p className="text-sm text-muted">—</p>}
      <ul className="space-y-3 text-xs">
        {rows?.map((c, i) => (
          <li key={i} className="space-y-1 border-t border-line pt-2">
            <p className="text-muted">
              {new Date(c.at).toLocaleString("ru-RU")} · {c.url}{c.translated ? " · translated" : ""}
            </p>
            <p className="font-medium">{c.message}</p>
            {c.stack && <pre className="max-h-48 overflow-auto whitespace-pre-wrap font-mono text-[10px] text-muted">{c.stack}</pre>}
            <p className="text-[10px] text-muted">{c.user_agent}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}
