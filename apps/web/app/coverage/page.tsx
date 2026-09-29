"use client";

import { useEffect, useState } from "react";
import { LevelBadge, type Level } from "@/components/LevelBadge";
import { CtaBanner } from "@/components/CtaBanner";
import { Alert, Button, Section } from "@/components/ui";
import { errorText, publicApi } from "@/lib/api";
import { useLang, useT } from "@/lib/i18n";

type LegalSource = { id: string; name: string; url: string; operator: string; kind: string };

type Coverage = {
  branches: { id: string; title: string; situation: string }[];
  countries: { country: string; name: string; status: string; cells: Record<string, Level>; legal_sources?: LegalSource[] }[];
};

const LEGEND: Level[] = ["verified", "scenario_draft", "universal", "lawyer", "soon"];

export default function CoveragePage() {
  const t = useT();
  const { lang } = useLang();
  const [data, setData] = useState<Coverage | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    publicApi<Coverage>(`/v1/coverage?lang=${lang}`).then(setData).catch((e) => setError(errorText(e)));
  }, [lang]);

  const live = data?.countries.filter((c) => c.status === "live") ?? [];
  const planned = data?.countries.filter((c) => c.status === "planned") ?? [];

  return (
    <div className="space-y-12">
      <header className="max-w-3xl space-y-3">
        <p className="eyebrow">{t("coverage.eyebrow")}</p>
        <h1 className="text-4xl font-semibold tracking-tight text-balance">{t("coverage.title")}</h1>
        <p className="text-lg text-muted">{t("coverage.lead")}</p>
      </header>

      {error && <Alert tone="danger" role="alert">{error}</Alert>}
      {!data && !error && <p className="text-muted">{t("common.loading")}</p>}

      {data && live.map((c) => (
        <Section key={c.country} title={c.name} lead={t("coverage.liveLead")}>
          {/* phones: a list; wide screens: the same list in columns — no horizontal page scroll */}
          <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {data.branches.map((b) => (
              <li key={b.id} className="flex items-center justify-between gap-3 rounded-2xl border border-line bg-surface p-3">
                <span className="text-sm font-medium">{b.title}</span>
                <LevelBadge level={c.cells[b.id] ?? "soon"} />
              </li>
            ))}
          </ul>
          {/* what the statuses mean: right under the list, folded */}
          <details className="card">
            <summary className="cursor-pointer font-semibold">{t("coverage.legend")}</summary>
            <ul className="mt-3 grid gap-3 md:grid-cols-2">
              {LEGEND.map((lv) => (
                <li key={lv} className="flex flex-col gap-1.5 sm:flex-row sm:items-start sm:gap-3">
                  <LevelBadge level={lv} /><span className="text-sm text-muted">{t(`level.${lv}.desc`)}</span>
                </li>
              ))}
            </ul>
          </details>
        </Section>
      ))}

      {planned.length > 0 && (
        <Section title={t("coverage.plannedTitle")} lead={t("coverage.plannedLead")}>
          <ul className="flex flex-wrap gap-2">
            {planned.map((c) => (
              <li key={c.country} className="rounded-full border border-line bg-surface px-3 py-1.5 text-sm">{c.name}</li>
            ))}
          </ul>
          <Waitlist countries={planned} />
        </Section>
      )}

      {data && data.countries.some((c) => c.legal_sources?.length) && (
        <Section title={t("coverage.sourcesTitle")} lead={t("coverage.sourcesLead")}>
          <div className="space-y-2">
            {live.filter((c) => c.legal_sources?.length).map((c) => <Sources key={c.country} c={c} />)}
            {/* countries that are not live yet: one folded row instead of a long list */}
            {planned.some((c) => c.legal_sources?.length) && (
              <details className="card">
                <summary className="cursor-pointer font-semibold">
                  {t("coverage.otherCountries", { n: planned.filter((c) => c.legal_sources?.length).length })}
                </summary>
                <div className="mt-3 space-y-2">
                  {planned.filter((c) => c.legal_sources?.length).map((c) => <Sources key={c.country} c={c} nested />)}
                </div>
              </details>
            )}
          </div>
        </Section>
      )}

      <CtaBanner />
    </div>
  );
}

function Sources({ c, nested = false }: { c: { name: string; legal_sources?: LegalSource[] }; nested?: boolean }) {
  const t = useT();
  return (
    <details className={nested ? "rounded-xl border border-line px-4 py-3" : "card"}>
      <summary className="cursor-pointer font-semibold">{c.name}</summary>
      <ul className="mt-3 space-y-2">
        {c.legal_sources!.map((s) => (
          <li key={s.id} className="text-sm">
            <a href={s.url} target="_blank" rel="noopener noreferrer" className="link break-words">{s.name}</a>
            <span className="block text-xs text-muted">{t(`coverage.sourceKind.${s.kind}`)} · {s.operator}</span>
          </li>
        ))}
      </ul>
    </details>
  );
}

function Waitlist({ countries }: { countries: { country: string; name: string }[] }) {
  const t = useT();
  const { lang } = useLang();
  const [country, setCountry] = useState(countries[0]?.country ?? "UZ");
  const [contact, setContact] = useState("");
  const [problem, setProblem] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await publicApi("/v1/waitlist", { method: "POST", body: JSON.stringify({ country, contact, problem: problem || null, language: lang }) });
      setSent(true);
    } catch (err) {
      setError(errorText(err));
    }
  }

  if (sent) return <Alert tone="info" icon="checkCircle" title={t("landing.waitlistDone")} />;
  return (
    <form onSubmit={submit} className="card max-w-xl space-y-3">
      <h3 className="font-semibold">{t("coverage.waitlistTitle")}</h3>
      <label className="block text-sm">{t("landing.countryTitle")}
        <select className="input mt-1" value={country} onChange={(e) => setCountry(e.target.value)}>
          {countries.map((c) => <option key={c.country} value={c.country}>{c.name}</option>)}
        </select>
      </label>
      <label className="block text-sm">{t("landing.waitlistContact")}
        <input className="input mt-1" required minLength={3} value={contact} onChange={(e) => setContact(e.target.value)} />
      </label>
      <label className="block text-sm">{t("landing.waitlistProblem")}
        <textarea className="input mt-1" rows={3} value={problem} onChange={(e) => setProblem(e.target.value)} />
      </label>
      <Button icon="mail">{t("landing.waitlistSend")}</Button>
      {error && <Alert tone="danger" role="alert">{error}</Alert>}
    </form>
  );
}
