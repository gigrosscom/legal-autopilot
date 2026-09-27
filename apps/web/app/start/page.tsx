"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { EmergencyPanel } from "@/components/EmergencyPanel";
import { Alert, Button, Icon, type IconName } from "@/components/ui";
import { useLang, useT } from "@/lib/i18n";
import { SITUATIONS } from "@/lib/situations";
import { useStartCase } from "@/lib/startCase";

// Official services people file through; the case explains which one fits and how.
const SERVICES: { key: string; name: string; url: string; icon: IconName }[] = [
  { key: "eotinish", name: "eOtinish", url: "https://eotinish.kz", icon: "send" },
  { key: "sud", name: "Судебный кабинет", url: "https://office.sud.kz", icon: "landmark" },
  { key: "egov", name: "eGov", url: "https://egov.kz", icon: "building" },
];

const stem = (w: string) => w.toLowerCase().replace(/[^\p{L}\p{N}]/gu, "").slice(0, 5);

export default function StartPage() {
  const t = useT();
  const { lang } = useLang();
  const [text, setText] = useState("");
  const [situation, setSituation] = useState<(typeof SITUATIONS)[number] | null>(null);
  const [allExamples, setAllExamples] = useState(false);
  const { start, busy, error, emergency, dismissEmergency } = useStartCase(lang);

  // ?s=<situation> from the home page tiles: a hint, not a choice of law — the text is still free.
  useEffect(() => {
    const key = new URLSearchParams(window.location.search).get("s");
    const s = SITUATIONS.find((x) => x.key === key) ?? null;
    setSituation(s);
  }, []);

  const examples = useMemo(() => {
    const n = Number(t("helper.exampleCount")) || 0;
    return Array.from({ length: n }, (_, i) => t(`helper.examples.${i + 1}`));
  }, [t]);

  // Autocomplete: examples sharing words with what is typed so far (a start, the text stays editable).
  const suggestions = useMemo(() => {
    const words = text.split(/\s+/).map(stem).filter((w) => w.length >= 4);
    if (!words.length || text.length > 120) return [];
    return examples
      .map((e) => ({ e, score: words.filter((w) => e.split(/\s+/).some((x) => stem(x) === w)).length }))
      .filter((x) => x.score > 0 && x.e !== text)
      .sort((a, b) => b.score - a.score)
      .slice(0, 3)
      .map((x) => x.e);
  }, [text, examples]);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    start(text.trim());
  }

  return (
    <form onSubmit={submit} className="mx-auto max-w-2xl space-y-5">
      <div className="space-y-2">
        <p className="eyebrow">{t("start.eyebrow")}</p>
        <h1 className="text-3xl font-bold tracking-tight">{t("start.title")}</h1>
        {situation && (
          <p className="flex items-center gap-2 text-muted">
            <Icon name={situation.icon} className="text-brand" />
            <span>{t(`situations.${situation.key}.hint`)}</span>
          </p>
        )}
      </div>

      {/* three steps: describe → answer and attach → download and file */}
      <ol className="grid gap-2 sm:grid-cols-3">
        {(["step1", "step2", "step3"] as const).map((k, i) => (
          <li key={k} className={`flex items-center gap-2 rounded-2xl border p-3 text-sm ${i === 0 ? "border-brand bg-brand-50" : "border-line bg-surface"}`}>
            <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-bold ${i === 0 ? "bg-brand text-white" : "bg-sand text-muted"}`}>{i + 1}</span>
            <span className={i === 0 ? "font-semibold" : "text-muted"}>{t(`helper.${k}`)}</span>
          </li>
        ))}
      </ol>

      <div className="space-y-2">
        <label htmlFor="story" className="sr-only">{t("home.describe")}</label>
        <textarea id="story" className="input min-h-40 resize-y" required minLength={10} autoFocus value={text}
          placeholder={situation ? t(`situations.${situation.key}.placeholder`) : t("start.placeholder")}
          onChange={(e) => setText(e.target.value)} />
        {suggestions.length > 0 && (
          <div className="space-y-1.5" aria-live="polite">
            <p className="flex items-center gap-1.5 text-xs font-semibold text-muted"><Icon name="sparkle" size={14} />{t("helper.suggestTitle")}</p>
            <ul className="space-y-1.5">
              {suggestions.map((s) => (
                <li key={s}>
                  <button type="button" onClick={() => setText(s)}
                    className="w-full rounded-xl border border-line bg-surface px-3 py-2 text-start text-sm hover:border-brand">{s}</button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {emergency && <EmergencyPanel info={emergency}
        onContinue={() => { dismissEmergency(); start(text.trim(), { skipTriage: true }); }} />}
      {error && <Alert tone="danger" role="alert">{error}</Alert>}
      <Button size="lg" className="w-full sm:w-auto" disabled={busy || text.trim().length < 10}
        icon={busy ? "spinner" : undefined} iconEnd={busy ? undefined : "arrowRight"}>
        {busy ? t("start.busy") : t("start.submit")}
      </Button>

      {!text.trim() && (
        <div className="space-y-2">
          <p className="text-sm font-semibold">{t("helper.examplesTitle")}</p>
          <div className="flex flex-wrap gap-2">
            {(allExamples ? examples : examples.slice(0, 6)).map((e) => (
              <button key={e} type="button" onClick={() => setText(e)}
                className="min-h-10 rounded-full border border-line bg-surface px-3 py-2 text-start text-sm hover:border-brand hover:text-brand">{e}</button>
            ))}
            {!allExamples && examples.length > 6 && (
              <button type="button" onClick={() => setAllExamples(true)} className="link inline-flex min-h-10 items-center px-2 text-sm">{t("helper.more")}</button>
            )}
          </div>
        </div>
      )}

      <div className="space-y-2 border-t border-line pt-4">
        <p className="text-sm font-semibold">{t("helper.servicesTitle")}</p>
        <ul className="grid gap-2 sm:grid-cols-3">
          {SERVICES.map((s) => (
            <li key={s.key}>
              <a href={s.url} target="_blank" rel="noreferrer" className="flex h-full items-start gap-2 rounded-2xl border border-line bg-surface p-3 text-sm hover:border-brand">
                <Icon name={s.icon} size={18} className="mt-0.5 text-brand" />
                <span><span className="block font-semibold">{s.name}</span><span className="text-muted">{t(`helper.${s.key}`)}</span></span>
              </a>
            </li>
          ))}
        </ul>
      </div>

      <p className="text-xs text-muted">{t("start.country")} <Link href="/coverage" className="link">{t("start.otherCountry")}</Link></p>
      <p className="text-xs text-muted">{t("landing.disclaimer")}</p>
    </form>
  );
}
