"use client";

import { useCallback, useEffect, useState, type ReactNode } from "react";
import { money } from "@/components/LawyerPilot";
import { Alert, Badge, Button, Icon } from "@/components/ui";
import { api, downloadFile, errorText } from "@/lib/api";
import { useT } from "@/lib/i18n";

type Req = {
  id: number; status: "new" | "accepted" | "declined" | "paid" | "closed"; case_id: string; created_at: string;
  price: number | null; currency: string; commission_pct: number;
  summary: { title: string | null; category: string | null; city: string | null; amount_at_stake: string | null;
    currency: string | null };
  client: { name: string; phone: string; email: string | null } | null;
  direct?: boolean;      // the client pays the lawyer directly (owner 01.10); 15 % to the platform monthly
  commission?: number;   // direct, paid: the platform's commission for the month's bill
};
type Dossier = {
  case_id: string; title: string | null; status_label: string;
  client: { name: string; phone: string; email: string | null };
  initial_text: string | null; narrative: string | null; story: string[];
  facts: { field: string; label: string; value: string }[];
  evidence: { id: string; kind: string; filename: string | null; has_file: boolean; text: string | null }[];
  deadlines: { due_date: string; status: string; norm_ref: string | null }[];
  documents: { id: string; title: string; status: string; has_pdf: boolean; has_docx: boolean }[];
};

const TONE = { new: "info", accepted: "brand", declined: "neutral", paid: "brand", closed: "neutral" } as const;

/** The lawyer's side of «Юрист по кнопке»: requests to accept or decline, and the dossier of each paid case. */
export function LawyerRequests() {
  const t = useT();
  const [rows, setRows] = useState<Req[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<number | null>(null);
  const load = useCallback(() => api<Req[]>("/v1/lawyer/requests").then(setRows).catch((e) => setError(errorText(e))), []);
  useEffect(() => { load(); }, [load]);

  async function answer(id: number, what: "accept" | "decline" | "client-paid") {
    setBusy(id);
    setError(null);
    try {
      await api(`/v1/lawyer/requests/${id}/${what}`, { method: "POST" });
      await load();
    } catch (e) { setError(errorText(e)); } finally { setBusy(null); }
  }

  if (!rows) return error ? <Alert tone="danger" role="alert">{error}</Alert> : null;
  return (
    <section aria-labelledby="requests-title" className="space-y-3">
      <h2 id="requests-title" className="text-xl font-semibold">{t("lawyer.requests.title")}</h2>
      {error && <Alert tone="danger" role="alert">{error}</Alert>}
      {rows.length === 0 && <p className="text-muted">{t("lawyer.requests.empty")}</p>}
      <ul className="space-y-3">
        {rows.map((r) => {
          const price = r.price ?? 0;
          const fee = Math.round(price * r.commission_pct) / 100;
          return (
            <li key={r.id} className="card space-y-3">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <p className="font-semibold">{r.summary.title ?? t("case.untitled")}</p>
                <Badge tone={TONE[r.status]}>{t(`lawyer.requests.status.${r.status}`)}</Badge>
              </div>
              <dl className="grid gap-2 text-sm sm:grid-cols-2">
                {r.summary.category && <Item label={t("lawyer.requests.category")} value={r.summary.category} />}
                {r.summary.city && <Item label={t("lawyer.requests.city")} value={r.summary.city} />}
                {r.summary.amount_at_stake && <Item label={t("lawyer.requests.amount")} value={`${r.summary.amount_at_stake} ${r.summary.currency ?? ""}`} />}
                <Item label={t("lawyer.requests.price")} value={money(price, r.currency)} />
                <Item label={t("lawyer.requests.payout", { pct: r.commission_pct })} value={money(price - fee, r.currency)} />
              </dl>
              {r.status === "new" && (
                <div className="flex gap-2">
                  <Button className="min-h-11 flex-1" disabled={busy === r.id} icon="check" onClick={() => answer(r.id, "accept")}>{t("lawyer.requests.accept")}</Button>
                  <Button variant="secondary" className="min-h-11" disabled={busy === r.id} onClick={() => answer(r.id, "decline")}>{t("lawyer.requests.decline")}</Button>
                </div>
              )}
              {r.status === "accepted" && !r.direct && <p className="text-sm text-muted">{t("lawyer.requests.waitPayment")}</p>}
              {r.status === "accepted" && r.direct && (
                <div className="space-y-2">
                  <p className="text-sm">{t("lawyer.requests.directNext")}</p>
                  <Button className="min-h-11 w-full" disabled={busy === r.id} icon="check" onClick={() => answer(r.id, "client-paid")}>
                    {t("lawyer.requests.clientPaid")}
                  </Button>
                </div>
              )}
              {r.status === "paid" && r.direct && r.commission != null && (
                <p className="text-sm text-muted">{t("lawyer.requests.commissionDue", { amount: money(r.commission, r.currency) })}</p>
              )}
              {r.client && (
                <p className="rounded-xl bg-sand p-3 text-sm">
                  <span className="block text-xs text-muted">{t("lawyer.requests.client")}</span>
                  {r.client.name} · <span dir="ltr">{r.client.phone}</span>{r.client.email ? ` · ${r.client.email}` : ""}
                </p>
              )}
              {(r.status === "paid" || r.status === "closed" || (r.direct && r.status === "accepted")) && <DossierView caseId={r.case_id} />}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function Item({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-sand p-2">
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="break-words">{value}</dd>
    </div>
  );
}

function DossierView({ caseId }: { caseId: string }) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const [d, setD] = useState<Dossier | null>(null);
  const [error, setError] = useState<string | null>(null);

  function toggle() {
    setOpen(!open);
    if (!d) api<Dossier>(`/v1/lawyer/cases/${caseId}/dossier`).then(setD).catch((e) => setError(errorText(e)));
  }
  const dl = (path: string, name: string) => downloadFile(path, name).catch((e) => setError(errorText(e)));

  return (
    <div className="space-y-3">
      <Button variant="secondary" className="w-full" icon="folder" aria-expanded={open} onClick={toggle}>
        {open ? t("lawyer.dossier.hide") : t("lawyer.dossier.open")}
      </Button>
      {open && error && <Alert tone="danger" role="alert">{error}</Alert>}
      {open && d && (
        <div className="space-y-4 text-sm">
          <Block title={t("lawyer.dossier.story")}>
            {d.initial_text && <p className="whitespace-pre-line">{d.initial_text}</p>}
            {d.story.filter((m) => m !== d.initial_text).map((m, i) => <p key={i} className="whitespace-pre-line border-s-2 border-line ps-3">{m}</p>)}
            {d.narrative && (<><p className="text-xs text-muted">{t("lawyer.dossier.narrative")}</p><p className="whitespace-pre-line">{d.narrative}</p></>)}
          </Block>
          <Block title={t("lawyer.dossier.facts")}>
            {d.facts.length === 0 ? <p className="text-muted">{t("lawyer.dossier.none")}</p> : (
              <dl className="grid gap-2 sm:grid-cols-2">{d.facts.map((f) => <Item key={f.field} label={f.label} value={f.value} />)}</dl>
            )}
          </Block>
          <Block title={t("lawyer.dossier.evidence")}>
            {d.evidence.length === 0 ? <p className="text-muted">{t("lawyer.dossier.none")}</p> : (
              <ul className="space-y-2">{d.evidence.map((e) => (
                <li key={e.id} className="flex flex-wrap items-center gap-2">
                  <Icon name="paperclip" size={18} className="text-brand" />
                  <span className="min-w-0 flex-1 break-words">{e.filename ?? e.kind}</span>
                  {e.has_file && <Button variant="secondary" icon="download"
                    onClick={() => dl(`/v1/lawyer/cases/${caseId}/evidence/${e.id}`, e.filename ?? "file")}>{t("lawyer.dossier.download")}</Button>}
                </li>))}
              </ul>
            )}
          </Block>
          <Block title={t("lawyer.dossier.deadlines")}>
            {d.deadlines.length === 0 ? <p className="text-muted">{t("lawyer.dossier.none")}</p> : (
              <ul className="space-y-1">{d.deadlines.map((x, i) => (
                <li key={i} className="flex items-center gap-2"><Icon name="calendar" size={18} className="text-brand" />
                  <span dir="ltr">{new Date(x.due_date).toLocaleDateString("ru-RU")}</span>{x.norm_ref ? ` · ${x.norm_ref}` : ""}</li>))}
              </ul>
            )}
          </Block>
          <Block title={t("lawyer.dossier.documents")}>
            {d.documents.length === 0 ? <p className="text-muted">{t("lawyer.dossier.none")}</p> : (
              <ul className="space-y-2">{d.documents.map((a) => (
                <li key={a.id} className="flex flex-wrap items-center gap-2">
                  <Icon name="document" size={18} className="text-brand" />
                  <span className="min-w-0 flex-1">{a.title}</span>
                  {a.has_pdf && <Button variant="secondary" icon="download"
                    onClick={() => dl(`/v1/lawyer/cases/${caseId}/actions/${a.id}/document?format=pdf`, `${a.title}.pdf`)}>PDF</Button>}
                  {a.has_docx && <Button variant="secondary" icon="download"
                    onClick={() => dl(`/v1/lawyer/cases/${caseId}/actions/${a.id}/document?format=docx`, `${a.title}.docx`)}>DOCX</Button>}
                </li>))}
              </ul>
            )}
          </Block>
        </div>
      )}
    </div>
  );
}

function Block({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="space-y-2">
      <h3 className="font-semibold">{title}</h3>
      {children}
    </div>
  );
}
