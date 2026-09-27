"use client";

import { useEffect, useState } from "react";
import { LevelBadge, type Level } from "@/components/LevelBadge";
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
        <h1 className="text-4xl font-bold tracking-tight text-balance">{t("coverage.title")}</h1>
        <p className="text-lg text-muted">{t("coverage.lead")}</p>
      </header>

      <div className="card space-y-3">
        <h2 className="font-semibold">{t("coverage.legend")}</h2>
        <ul className="grid gap-3 md:grid-cols-2">
          {LEGEND.map((lv) => (
            <li key={lv} className="flex flex-col gap-1.5 sm:flex-row sm:items-start sm:gap-3">
              <LevelBadge level={lv} /><span className="text-sm text-muted">{t(`level.${lv}.desc`)}</span>
            </li>
          ))}
        </ul>
      </div>

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
            {[...live, ...planned].filter((c) => c.legal_sources?.length).map((c) => (
              <details key={c.country} className="card" open={c.status === "live"}>
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
            ))}
          </div>
        </Section>
      )}
    </div>
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
