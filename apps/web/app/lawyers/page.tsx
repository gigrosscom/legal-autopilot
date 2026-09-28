"use client";

import { useEffect, useState } from "react";
import { Button, Icon } from "@/components/ui";
import { publicApi, errorText } from "@/lib/api";
import { useLang, useT } from "@/lib/i18n";

type Score = {
  total: number;
  effectiveness: number;
  vs_baseline: number;
  reliability: number;
  recovery: number;
  reviews: number;
  verified_cases: number;
  confidence: "low" | "medium" | "high";
};

type Lawyer = {
  id: string;
  name: string;
  title: string;
  organization: string;
  city: string;
  years: number;
  verified: { license: boolean; registry: string; identity: boolean };
  specializations: { key: string; label: string }[];
  languages: string[];
  price_from: number;
  pro_bono?: boolean;
  response_hours: number;
  reviews_count: number;
  results: { category: string; label: string; cases: number; success_rate: number | null; baseline: number | null; recovered: number }[];
  score: Score;
};

type Directory = { demo: boolean; disclaimer: string; currency: string; lawyers: Lawyer[] };

const money = (v: number, mln: string) => (v >= 1e6 ? `${(v / 1e6).toFixed(1)} ${mln}` : v.toLocaleString("ru-RU"));
const pct = (v: number) => `${Math.round(v * 100)}%`;

export default function LawyersPage() {
  const t = useT();
  const { lang } = useLang();
  const [data, setData] = useState<Directory | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [freeOnly, setFreeOnly] = useState(false);

  useEffect(() => {
    publicApi<Directory>(`/v1/lawyers?country=KZ&lang=${lang}`).then(setData).catch((e) => setError(errorText(e)));
  }, [lang]);

  const cur = data?.currency === "KZT" ? "₸" : data?.currency ?? "";

  return (
    <div className="space-y-8">
      <div className="mx-auto max-w-3xl space-y-4 pt-6 pb-4 text-center md:pt-10">
        <h1 className="text-[40px] font-semibold leading-[1.05] tracking-[-0.015em] text-balance text-ink md:text-[64px]">{t("lawyers.title")}</h1>
        <p className="text-[21px] leading-[1.38] text-muted text-pretty md:text-[24px]">{t("lawyers.subtitle")}</p>
      </div>

      {data?.demo && (
        <div role="note" className="rounded-2xl bg-warning-50 px-5 py-4 text-sm text-warning">{data.disclaimer}</div>
      )}
      {/* reserve the space the list will take, so nothing on screen jumps when it arrives */}
      {!data && !error && <p aria-busy="true" className="min-h-[80vh] text-muted">{t("common.loading")}</p>}
      {error && <p role="alert" className="rounded-xl bg-danger-50 p-3 text-sm text-danger">{error}</p>}

      {data && <p className="text-center text-sm text-muted">{t("lawyers.chooseSoon")}</p>}
      {data && (
        <div role="group" aria-label={t("lawyers.filter")} className="flex flex-wrap justify-center gap-2">
          {([false, true] as const).map((v) => (
            <button key={String(v)} type="button" aria-pressed={freeOnly === v} onClick={() => setFreeOnly(v)}
              className={`min-h-10 rounded-full px-5 text-sm transition-colors ${freeOnly === v ? "bg-ink text-white" : "bg-sand text-ink hover:bg-sand-deep"}`}>
              {v ? t("lawyers.freeOnly") : t("lawyers.all")}
            </button>
          ))}
          {freeOnly && <p className="basis-full text-center text-sm text-muted">{t("lawyers.freeNote")}</p>}
        </div>
      )}

      {data && <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        <div className="space-y-4">
          {freeOnly && !data.lawyers.some((l) => l.pro_bono) && <p className="text-muted">{t("lawyers.freeNone")}</p>}
          {data.lawyers.filter((l) => !freeOnly || l.pro_bono).map((l, i) => (
            <article key={l.id} className="space-y-5 rounded-3xl bg-sand p-6 md:p-8">
              <div className="flex items-start justify-between gap-4">
                <div className="flex min-w-0 flex-1 gap-3">
                  <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-surface text-lg font-semibold">
                    {i + 1}
                  </div>
                  <div>
                    <h2 className="text-[21px] font-semibold tracking-[-0.01em]">{l.name}</h2>
                    <p className="text-sm text-muted">
                      {l.title} · {l.organization} · {l.city} · {l.years} {t("lawyers.years")}
                    </p>
                    <div className="mt-1 flex flex-wrap gap-1 text-xs">
                      {l.verified.license && <span className="chip bg-brand-50 text-brand-dark">{t("lawyers.verifiedLicense")}</span>}
                      {l.verified.identity && <span className="chip bg-brand-50 text-brand-dark">{t("lawyers.verifiedId")}</span>}
                      {l.specializations.map((s) => <span key={s.key} className="chip bg-surface">{s.label}</span>)}
                    </div>
                  </div>
                </div>
                <div className="text-end">
                  <div className="text-[40px] leading-none font-semibold tracking-[-0.015em] text-ink">{l.score.total}<span className="text-sm font-medium text-muted">/100</span></div>
                  <div className="text-xs text-muted">{t("lawyers.score")}</div>
                </div>
              </div>

              <dl className="grid grid-cols-2 gap-3 text-sm">
                <Metric label={t("lawyers.cases")} value={String(l.score.verified_cases)} />
                <Metric label={t("lawyers.onTime")} value={pct(l.score.reliability)} />
              </dl>

              <details className="group rounded-2xl bg-surface px-4 py-2 text-sm">
                <summary className="flex min-h-10 cursor-pointer list-none items-center justify-between font-medium">
                  {t("lawyers.details")}<Icon name="chevronDown" size={16} className="transition-transform group-open:rotate-180" />
                </summary>
                <div className="space-y-3 pt-2">
              <dl className="grid grid-cols-2 gap-3 text-sm">
                <Metric
                  label={t("lawyers.vsBaseline")}
                  value={`${l.score.vs_baseline > 0 ? "+" : ""}${l.score.vs_baseline} ${t("lawyers.pp")}`}
                  tone={l.score.vs_baseline >= 0 ? "good" : "bad"}
                />
                <Metric label={t("lawyers.reviews")} value={`${l.score.reviews.toFixed(1)} ★ (${l.reviews_count})`} />
              </dl>

              <div className="space-y-2">
                {l.results.map((r) => (
                  <div key={r.category} className="text-sm">
                    <div className="flex justify-between gap-2">
                      <span>{r.label} — {r.cases}</span>
                      <span className="text-muted">
                        {t("lawyers.success")} {r.success_rate != null ? pct(r.success_rate) : "—"}
                        {r.baseline != null && ` · ${t("lawyers.platform")} ${pct(r.baseline)}`}
                        {` · ${t("lawyers.recovered")} ${money(r.recovered, t("lawyers.mln"))} ${cur}`}
                      </span>
                    </div>
                    <div className="relative mt-1 h-2 rounded-full bg-sand-deep">
                      <div className="h-2 rounded-full bg-action" style={{ width: pct(r.success_rate ?? 0) }} />
                      {r.baseline != null && (
                        <div className="absolute top-[-3px] h-3.5 w-0.5 bg-ink/60" style={{ left: pct(r.baseline) }} title={t("lawyers.platform")} />
                      )}
                    </div>
                  </div>
                ))}
              </div>

                </div>
              </details>

              <div className="flex flex-wrap items-center justify-between gap-2 border-t border-line pt-4 text-sm">
                <span className="text-muted">
                  {l.pro_bono ? t("lawyers.proBono") : `${t("lawyers.from")} ${l.price_from.toLocaleString("ru-RU")} ${cur}`}
                  {` · ${t("lawyers.response")} ${l.response_hours} ${t("lawyers.hours")}`}
                </span>
                <Button href={`/lawyers/request?lawyer=${encodeURIComponent(l.id)}&name=${encodeURIComponent(l.name)}`} variant="secondary" iconEnd="arrowRight">{t("lawyers.choose")}</Button>
              </div>
            </article>
          ))}
        </div>

        <aside className="card h-fit space-y-3 text-sm lg:sticky lg:top-20">
          <h2 className="text-[17px] font-semibold">{t("lawyers.methodTitle")}</h2>
          <ol className="list-inside list-decimal space-y-2 text-muted">
            {["method1", "method2", "method3", "method4"].map((k) => <li key={k}>{t(`lawyers.${k}`)}</li>)}
          </ol>
          <div className="space-y-2 border-t border-line pt-4">
            <p className="text-muted">{t("cta.lawyersLead")}</p>
            <Button href="/start" className="w-full" iconEnd="arrowRight">{t("cta.startCase")}</Button>
            <Button href="/for-lawyers" className="w-full" variant="secondary">{t("cta.join")}</Button>
          </div>
        </aside>
      </div>}
    </div>
  );
}

function Metric({ label, value, tone }: { label: string; value: string; tone?: "good" | "bad" }) {
  return (
    <div className="rounded-xl bg-surface px-3 py-2.5">
      <dt className="text-xs text-muted">{label}</dt>
      <dd className={`text-[17px] font-semibold ${tone === "good" ? "text-success" : tone === "bad" ? "text-danger" : ""}`}>{value}</dd>
    </div>
  );
}
