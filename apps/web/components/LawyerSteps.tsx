"use client";

import { LAWYERS_PUBLIC } from "@/lib/features";
import { Button, Icon } from "@/components/ui";
import { useT } from "@/lib/i18n";

export type LawyerStatus = {
  applied: boolean; hasEcp: boolean; status: "new" | "verified" | "rejected" | null; rejectReason?: string | null;
};

/** Where the lawyer is on the way in: application → ЭЦП → status check → cases. One next action at a time. */
export function LawyerSteps({ s }: { s: LawyerStatus }) {
  const t = useT();
  const steps = [
    { key: "applied", done: s.applied },
    { key: "ecp", done: s.hasEcp },
    { key: "check", done: s.status === "verified", failed: s.status === "rejected" },
    { key: "access", done: s.status === "verified" && s.hasEcp },
  ];
  const current = steps.findIndex((x) => !x.done);
  return (
    <ol className="card space-y-4" aria-label={t("lawyer.steps.title")}>
      {steps.map((x, i) => {
        const state = x.done ? "done" : i === current ? "current" : "todo";
        return (
          <li key={x.key} className="flex gap-3">
            <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm font-semibold ${
              x.failed ? "bg-danger text-white" : state === "done" ? "bg-brand text-white" : state === "current" ? "border-2 border-brand text-brand" : "bg-sand text-muted"}`}>
              {state === "done" ? <Icon name="check" size={16} /> : i + 1}
            </span>
            <div className="min-w-0 flex-1 space-y-1 pt-1">
              <p className={`font-semibold ${state === "todo" ? "text-muted" : ""}`}>{t(`lawyer.steps.${x.key}`)}</p>
              {state === "current" && !x.failed && <p className="text-sm text-muted">{t(`lawyer.steps.${x.key}Hint`)}</p>}
              {x.failed && <p className="text-sm text-danger">{t("lawyer.status.rejected")}</p>}
              {x.failed && s.rejectReason && <p className="text-sm text-danger">{t("lawyer.status.rejectedReason", { reason: s.rejectReason })}</p>}
              {x.failed && LAWYERS_PUBLIC && <Button href="/for-lawyers#apply" variant="secondary" iconEnd="arrowRight">{t("lawyer.apply")}</Button>}
              {state === "current" && x.key === "applied" && LAWYERS_PUBLIC && (
                <Button href="/for-lawyers#apply" iconEnd="arrowRight">{t("lawyer.apply")}</Button>
              )}
              {state === "current" && x.key === "ecp" && (
                <Button href="/account?method=ecp&next=/lawyer" icon="key">{t("lawyer.steps.ecpDo")}</Button>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
