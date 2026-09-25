"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type CaseView } from "@/lib/api";
import { useT } from "@/lib/i18n";

export default function CasesPage() {
  const t = useT();
  const [cases, setCases] = useState<CaseView[] | null>(null);
  useEffect(() => {
    api<CaseView[]>("/v1/cases").then(setCases).catch(() => setCases([]));
  }, []);
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">{t("cases.title")}</h1>
      {cases?.length === 0 && <p className="text-ink/60">{t("cases.empty")}</p>}
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
