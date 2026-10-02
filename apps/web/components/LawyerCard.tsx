"use client";

import type { ReactNode } from "react";
import { Badge, Icon } from "@/components/ui";
import { initials, type ChoiceLawyer } from "@/lib/demoLawyers";
import { useT } from "@/lib/i18n";

export function money(amount: number): string {
  return `${amount.toLocaleString("ru-RU").replace(/ /g, " ")} ₸`;
}

/** One lawyer to choose: initials (no photos), name, status, city, what they do, the rating by results when there is
 *  one, price, how fast they answer, and the action. A demo profile says so on the card itself. */
export function LawyerCard({ l, action }: { l: ChoiceLawyer; action: ReactNode }) {
  const t = useT();
  return (
    <li className="card space-y-3">
      {l.demo && <p className="inline-flex rounded-full bg-warning-50 px-2.5 py-0.5 text-xs font-semibold text-warning">{t("choose.sample")}</p>}
      <div className="flex items-start gap-3">
        <span aria-hidden className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-brand-50 text-base font-semibold text-brand">
          {initials(l.name)}
        </span>
        <div className="min-w-0 flex-1">
          <p className="font-semibold leading-snug">{l.name}</p>
          <p className="text-sm text-muted">{[l.kind, l.organization, l.city].filter(Boolean).join(" · ")}</p>
        </div>
      </div>
      <p className="flex flex-wrap items-baseline gap-x-2">
        <span className="text-lg font-semibold tabular-nums">{l.price ? money(l.price) : t("choose.free")}</span>
        {l.priceNote && <span className="text-sm text-muted">{l.priceNote}</span>}
      </p>
      {l.specializations.length > 0 && (
        <ul className="flex flex-wrap gap-2">{l.specializations.map((s) => <li key={s}><Badge tone="brand">{s}</Badge></li>)}</ul>
      )}
      <dl className="grid grid-cols-2 gap-2 text-sm">
        <div className="rounded-xl bg-sand px-3 py-2">
          <dt className="text-xs text-muted">{t("choose.rating")}</dt>
          <dd className="font-semibold">
            {l.rating
              ? <span className="inline-flex items-center gap-1"><Icon name="shieldCheck" size={16} className="text-brand" />{l.rating.score.toFixed(1)} · {Math.round(l.rating.success * 100)} %</span>
              : <span className="font-normal text-muted">{t("choose.noRating")}</span>}
          </dd>
          {l.rating && <dd className="text-xs text-muted">{t("choose.ratingNote", { cases: l.rating.cases, reviews: l.rating.reviews })}</dd>}
        </div>
        <div className="rounded-xl bg-sand px-3 py-2">
          <dt className="text-xs text-muted">{t("choose.response")}</dt>
          <dd className="font-semibold">{l.response}</dd>
        </div>
      </dl>
      {action}
    </li>
  );
}
