"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Alert, Button, Icon } from "@/components/ui";
import { api, downloadFile, errorText, type CaseAction, type CaseView } from "@/lib/api";
import { useT } from "@/lib/i18n";

type Doc = { a: CaseAction; c: CaseView; caseTitle: string };

/** Every document draft across the person's cases: status, download, the way back to its case. */
export default function DocumentsPage() {
  const t = useT();
  const [cases, setCases] = useState<CaseView[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");
  useEffect(() => { api<CaseView[]>("/v1/cases").then(setCases).catch((e) => setError(errorText(e))); }, []);

  const docs: Doc[] = useMemo(() => (cases ?? []).flatMap((c) => c.actions
    .filter((a) => a.kind !== "handoff" && (a.downloadable || a.has_pdf || a.has_docx))
    .map((a) => ({ a, c, caseTitle: c.scenario?.title ?? c.coverage?.dispute?.title ?? t("case.untitled") }))), [cases, t]);
  const shown = docs.filter((d) => !q.trim() || `${d.a.title} ${d.caseTitle}`.toLowerCase().includes(q.trim().toLowerCase()));

  const status = (a: CaseAction) => a.submitted_at || ["submitted", "responded"].includes(a.status) ? t("app.docs.submitted")
    : a.approval_status === "pending" ? t("app.docs.draft") : t("app.docs.ready");

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-1.5">
          <h1 className="text-3xl font-semibold tracking-tight md:text-4xl">{t("app.docs.title")}</h1>
          <p className="text-muted">{t("app.docs.lead")}</p>
        </div>
        <Button href="/start" iconEnd="plus" className="min-h-12">{t("app.docs.create")}</Button>
      </div>

      {docs.length > 0 && (
        <label className="relative block">
          <span className="sr-only">{t("app.docs.search")}</span>
          <svg aria-hidden width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" className="pointer-events-none absolute start-4 top-1/2 -translate-y-1/2 text-muted"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>
          <input className="input min-h-12 ps-12" type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("app.docs.search")} />
        </label>
      )}

      {!cases && !error && <p className="text-muted">{t("common.loading")}</p>}
      {error && <Alert tone="danger" role="alert">{error}</Alert>}

      {cases && docs.length === 0 && (
        <div className="flex flex-col items-center gap-3 rounded-2xl border border-dashed border-line px-6 py-14 text-center">
          <Icon name="document" size={36} className="text-muted" />
          <h2 className="text-xl font-semibold">{t("app.docs.empty")}</h2>
          <p className="max-w-md text-muted">{t("app.docs.emptyHint")}</p>
          <Button href="/start" variant="secondary" iconEnd="plus" className="mt-2 min-h-12">{t("app.docs.create")}</Button>
        </div>
      )}

      {shown.length > 0 && (
        <>
          <p className="text-sm font-semibold text-ink">{t("app.docs.count", { n: shown.length })}</p>
          <ul className="divide-y divide-line rounded-2xl border border-line">
            {shown.map(({ a, c, caseTitle }) => (
              <li key={a.id} className="space-y-4 p-4">
                {/* the whole head opens the case (owner's iPhone 04.10: three pill buttons in a row broke «Открыть дело» onto two
                    lines and cut the title); the document's own actions stay as two equal buttons under it */}
                <Link href={`/case/${c.id}`} aria-label={`${t("app.docs.open")}: ${a.title}`}
                  className="-mx-2 -mt-2 flex items-start gap-3 rounded-xl px-2 pt-2 pb-1 hover:bg-sand">
                  <Icon name="document" size={22} className="mt-0.5 shrink-0 text-ink" />
                  <div className="min-w-0 flex-1 space-y-1">
                    <p className="line-clamp-2 font-medium leading-snug text-balance text-ink">{a.title}</p>
                    <p className="truncate text-sm text-muted">{caseTitle}</p>
                    <span className="chip">{status(a)}</span>
                  </div>
                  <Icon name="chevronDown" size={20} className="mt-0.5 shrink-0 -rotate-90 text-muted rtl:rotate-90" />
                </Link>
                {(a.has_pdf || a.has_docx) && (
                  <div className="flex gap-2">
                    {a.has_pdf && (
                      <button type="button" onClick={() => downloadFile(`/v1/cases/${c.id}/actions/${a.id}/document?format=pdf`, `${a.action_id}.pdf`)}
                        className="btn-ghost flex-1 whitespace-nowrap sm:flex-none"><Icon name="download" size={16} />PDF</button>
                    )}
                    {a.has_docx && (
                      <button type="button" onClick={() => downloadFile(`/v1/cases/${c.id}/actions/${a.id}/document?format=docx`, `${a.action_id}.docx`)}
                        className="btn-ghost flex-1 whitespace-nowrap sm:flex-none"><Icon name="download" size={16} />DOCX</button>
                    )}
                  </div>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
