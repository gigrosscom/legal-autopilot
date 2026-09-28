"use client";

import { useEffect, useState } from "react";
import { CaseBoard, type BoardCard } from "@/components/CaseBoard";
import { Alert, Button } from "@/components/ui";
import { api, errorText, type CaseView } from "@/lib/api";
import { useT } from "@/lib/i18n";

export default function CasesPage() {
  const t = useT();
  const [cases, setCases] = useState<CaseView[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api<CaseView[]>("/v1/cases").then(setCases).catch((e) => setError(errorText(e)));
  }, []);

  const cards: BoardCard[] = (cases ?? []).map((c) => {
    const pendingApproval = c.actions.some((a) => a.approval_status === "pending");
    const expired = c.actions.some((a) => a.deadline?.status === "expired");
    const attention = c.safety?.hold_reason ? t("board.attention.hold")
      : c.safety?.pending_ack ? t("board.attention.ack")
      : expired ? t("board.attention.expired")
      : pendingApproval ? t("board.attention.approval")
      : c.status === "intake" && c.coverage?.options?.length && !c.scenario ? t("board.attention.chooseForum")
      : null;
    return {
      id: c.id,
      href: `/case/${c.id}`,
      title: c.scenario?.title ?? c.coverage?.dispute?.title ?? t("case.untitled"),
      stage: c.stage,
      level: c.coverage?.level ?? "verified",
      date: new Date(c.created_at).toLocaleDateString("ru-RU"),
      meta: c.coverage?.forum?.name,
      attention,
      tasks: c.actions.filter((a) => a.kind !== "handoff").map((a) => ({
        label: a.title, done: ["submitted", "responded"].includes(a.status),
      })),
    };
  });

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-3xl font-semibold tracking-tight">{t("cases.title")}</h1>
          <p className="text-muted">{t("cases.lead")}</p>
        </div>
        {cases && cases.length > 0 && <Button href="/start" icon="plus">{t("cases.new")}</Button>}
      </div>
      {!cases && !error && <p className="text-muted">{t("common.loading")}</p>}
      {error && <Alert tone="danger" role="alert">{error}</Alert>}
      {cases?.length === 0 && (
        <div className="card flex flex-col items-start gap-3">
          <p className="font-semibold">{t("cases.empty")}</p>
          <p className="text-sm text-muted">{t("cases.emptyHint")}</p>
          <Button href="/start" size="lg" iconEnd="arrowRight">{t("home.cta")}</Button>
        </div>
      )}
      {cases && cases.length > 0 && <CaseBoard cards={cards} />}
    </div>
  );
}
