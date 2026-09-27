"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, errorText, type CaseView } from "@/lib/api";
import { useT } from "@/lib/i18n";

export default function CasesPage() {
  const t = useT();
  const [cases, setCases] = useState<CaseView[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api<CaseView[]>("/v1/cases").then(setCases).catch((e) => setError(errorText(e)));
  }, []);
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">{t("cases.title")}</h1>
      {!cases && !error && <p className="text-ink/50">{t("common.loading")}</p>}
      {error && <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-red-700">{error}</p>}
      {cases?.length === 0 && (
        <div className="card space-y-3">
          <p className="text-ink/60">{t("cases.empty")}</p>
          <Link href="/start" className="btn-primary">{t("nav.start")} →</Link>
        </div>
      )}
      <div className="space-y-3">
        {cases?.map((c) => (
          <Link key={c.id} href={`/case/${c.id}`} className="card flex items-center justify-between hover:border-brand">
            <div>
              <div className="font-semibold">{c.scenario?.title ?? "—"}</div>
              <div className="text-xs text-ink/50">{new Date(c.created_at).toLocaleDateString("ru-RU")}</div>
            </div>
            <span className="chip">{c.status_label}</span>
          </Link>
        ))}
      </div>
    </div>
  );
}
