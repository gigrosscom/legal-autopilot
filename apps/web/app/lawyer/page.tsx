"use client";

import { LAWYERS_PUBLIC } from "@/lib/features";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Agreements } from "@/components/Agreements";
import { LawyerRequests } from "@/components/LawyerRequests";
import { LawyerSteps, type LawyerStatus } from "@/components/LawyerSteps";
import { Alert, Badge, Button, Icon } from "@/components/ui";
import { ApiError, api, downloadFile, errorText, type CaseLawyer, type CaseView } from "@/lib/api";
import { useT } from "@/lib/i18n";

type LawyerMe = { applications: { id: number; status: string; name: string; kind: string; reject_reason?: string | null }[]; verified: boolean; has_ecp: boolean };
type LawyerCase = CaseView & CaseLawyer;

export default function LawyerCabinet() {
  const t = useT();
  const [me, setMe] = useState<LawyerMe | null>(null);
  const [cases, setCases] = useState<LawyerCase[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<LawyerMe>("/v1/lawyer/me").then((m) => {
      setMe(m);
      if (m.verified) api<LawyerCase[]>("/v1/lawyer/cases").then(setCases).catch((e) => setError(errorText(e)));
    }).catch((e) => setError(e instanceof ApiError ? errorText(e) : errorText(e)));
  }, []);

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div className="space-y-2">
        <p className="eyebrow">{t("lawyer.eyebrow")}</p>
        <h1 className="text-3xl font-semibold tracking-tight">{t("lawyer.title")}</h1>
        <p className="text-muted">{t("lawyer.lead")}</p>
      </div>
      {error && <Alert tone="danger" role="alert">{error}</Alert>}

      {me && !(me.verified && me.has_ecp) && (
        <LawyerSteps s={{ applied: me.applications.length > 0, hasEcp: me.has_ecp,
          status: (me.applications[0]?.status as LawyerStatus["status"]) ?? null,
          rejectReason: me.applications[0]?.reject_reason ?? null }} />
      )}

      {me?.verified && <LawyerRequests />}

      {cases && cases.length > 0 && <h2 className="text-xl font-semibold">{t("lawyer.casesTitle")}</h2>}
      {cases && cases.length === 0 && <p className="text-muted">{t("lawyer.noCases")}</p>}
      {cases?.map((c) => (
        <section key={c.id} className="space-y-3" aria-labelledby={`case-${c.id}`}>
          <div className="card space-y-3">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <h2 id={`case-${c.id}`} className="text-lg font-semibold">
                {c.scenario?.title ?? c.coverage?.dispute?.title ?? t("case.untitled")}
              </h2>
              <Badge>{c.status_label}</Badge>
            </div>
            <dl className="grid gap-2 text-sm sm:grid-cols-2">
              {c.facts.map((f) => (
                <div key={f.field} className="rounded-lg bg-sand p-2">
                  <dt className="text-xs text-muted">{f.label}</dt>
                  <dd className="break-words">{f.value}</dd>
                </div>
              ))}
            </dl>
            {c.actions.filter((a) => a.kind === "document" && a.downloadable).map((a) => (
              <div key={a.id} className="flex flex-wrap items-center gap-2 text-sm">
                <Icon name="document" size={18} className="text-brand" />
                <span className="flex-1">{a.sequence}. {a.title}</span>
                {a.has_pdf && <Button variant="secondary" icon="download"
                  onClick={() => downloadFile(`/v1/lawyer/cases/${c.id}/actions/${a.id}/document?format=pdf`, `${a.action_id}.pdf`)}>PDF</Button>}
                <Button variant="secondary" icon="download"
                  onClick={() => downloadFile(`/v1/lawyer/cases/${c.id}/actions/${a.id}/document?format=docx`, `${a.action_id}.docx`)}>DOCX</Button>
              </div>
            ))}
          </div>
          <Agreements items={c.agreements} role="lawyer" />
        </section>
      ))}

      {LAWYERS_PUBLIC && <p className="text-sm text-muted"><Link className="link" href="/for-lawyers">{t("lawyer.aboutProgram")}</Link></p>}
    </div>
  );
}
