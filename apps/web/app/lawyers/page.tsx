"use client";

import { useEffect, useState } from "react";
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

const money = (v: number) => (v >= 1e6 ? `${(v / 1e6).toFixed(1)} млн` : v.toLocaleString("ru-RU"));
const pct = (v: number) => `${Math.round(v * 100)}%`;

export default function LawyersPage() {
  const t = useT();
  const { lang } = useLang();
  const [data, setData] = useState<Directory | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    publicApi<Directory>(`/v1/lawyers?country=KZ&lang=${lang}`).then(setData).catch((e) => setError(errorText(e)));
  }, [lang]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">{t("lawyers.title")}</h1>
        <p className="text-ink/70">{t("lawyers.subtitle")}</p>
      </div>

      {data?.demo && (
        <div className="rounded-xl border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">⚠️ {data.disclaimer}</div>
      )}
      {!data && !error && <p className="text-ink/50">{t("common.loading")}</p>}
      {error && <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-red-700">{error}</p>}

      <div className="grid gap-6 lg:grid-cols-[1fr_300px]">
        <div className="space-y-4">
          {data?.lawyers.map((l, i) => (
            <article key={l.id} className="card space-y-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="flex gap-3">
                  <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-ink/5 text-lg font-bold">
                    {i + 1}
                  </div>
                  <div>
                    <h2 className="text-lg font-semibold">{l.name}</h2>
                    <p className="text-sm text-ink/60">
                      {l.title} · {l.organization} · {l.city} · {l.years} {t("lawyers.years")}
                    </p>
                    <div className="mt-1 flex flex-wrap gap-1 text-xs">
                      {l.verified.license && <span className="chip bg-brand/10 text-brand">✓ {t("lawyers.verifiedLicense")}</span>}
                      {l.verified.identity && <span className="chip bg-brand/10 text-brand">✓ {t("lawyers.verifiedId")}</span>}
                      {l.specializations.map((s) => <span key={s.key} className="chip">{s.label}</span>)}
                    </div>
                  </div>
                </div>
                <div className="text-right">
                  <div className="text-3xl font-bold text-brand">{l.score.total}</div>
                  <div className="text-xs text-ink/50">{t("lawyers.score")} · {t(`lawyers.confidence.${l.score.confidence}`)}</div>
                </div>
              </div>

              <dl className="grid grid-cols-2 gap-3 text-sm md:grid-cols-4">
                <Metric label={t("lawyers.cases")} value={String(l.score.verified_cases)} />
                <Metric
                  label={t("lawyers.vsBaseline")}
                  value={`${l.score.vs_baseline > 0 ? "+" : ""}${l.score.vs_baseline} п.п.`}
                  tone={l.score.vs_baseline >= 0 ? "good" : "bad"}
                />
                <Metric label={t("lawyers.onTime")} value={pct(l.score.reliability)} />
                <Metric label={t("lawyers.reviews")} value={`${l.score.reviews.toFixed(1)} ★ (${l.reviews_count})`} />
              </dl>

              <div className="space-y-2">
                {l.results.map((r) => (
                  <div key={r.category} className="text-sm">
                    <div className="flex justify-between gap-2">
                      <span>{r.label} — {r.cases}</span>
                      <span className="text-ink/60">
                        {t("lawyers.success")} {r.success_rate != null ? pct(r.success_rate) : "—"}
                        {r.baseline != null && ` · ${t("lawyers.platform")} ${pct(r.baseline)}`}
                        {` · ${t("lawyers.recovered")} ${money(r.recovered)} ${data.currency}`}
                      </span>
                    </div>
                    <div className="relative mt-1 h-2 rounded-full bg-ink/5">
                      <div className="h-2 rounded-full bg-brand" style={{ width: pct(r.success_rate ?? 0) }} />
                      {r.baseline != null && (
                        <div className="absolute top-[-3px] h-3.5 w-0.5 bg-ink/60" style={{ left: pct(r.baseline) }} title={t("lawyers.platform")} />
                      )}
                    </div>
                  </div>
                ))}
              </div>

              <div className="flex flex-wrap items-center justify-between gap-2 border-t border-ink/10 pt-3 text-sm">
                <span className="text-ink/70">
                  {l.pro_bono ? t("lawyers.proBono") : `${t("lawyers.from")} ${l.price_from.toLocaleString("ru-RU")} ${data.currency}`}
                  {` · ${t("lawyers.response")} ${l.response_hours} ${t("lawyers.hours")}`}
                </span>
                <button className="btn-ghost" disabled title={t("lawyers.chooseSoon")}>{t("lawyers.choose")}</button>
              </div>
            </article>
          ))}
        </div>

        <aside className="card h-fit space-y-2 text-sm">
          <h2 className="font-semibold">{t("lawyers.methodTitle")}</h2>
          <ol className="list-inside list-decimal space-y-2 text-ink/70">
            {["method1", "method2", "method3", "method4"].map((k) => <li key={k}>{t(`lawyers.${k}`)}</li>)}
          </ol>
          <p className="border-t border-ink/10 pt-2 text-xs text-ink/50">{t("lawyers.chooseSoon")}</p>
        </aside>
      </div>
    </div>
  );
}

function Metric({ label, value, tone }: { label: string; value: string; tone?: "good" | "bad" }) {
  return (
    <div className="rounded-xl bg-ink/5 p-2">
      <dt className="text-xs text-ink/50">{label}</dt>
      <dd className={`font-semibold ${tone === "good" ? "text-brand" : tone === "bad" ? "text-red-600" : ""}`}>{value}</dd>
    </div>
  );
}
