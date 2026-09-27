"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { EmergencyPanel } from "@/components/EmergencyPanel";
import { Alert, Button, Icon } from "@/components/ui";
import { useLang, useT } from "@/lib/i18n";
import { SITUATIONS } from "@/lib/situations";
import { useStartCase } from "@/lib/startCase";

export default function StartPage() {
  const t = useT();
  const { lang } = useLang();
  const [text, setText] = useState("");
  const [situation, setSituation] = useState<(typeof SITUATIONS)[number] | null>(null);
  const [religious, setReligious] = useState(false);
  const { start, busy, error, emergency, dismissEmergency } = useStartCase(lang);

  // ?s=<situation> from the home page tiles: a hint, not a choice of law — the text is still free.
  useEffect(() => {
    const key = new URLSearchParams(window.location.search).get("s");
    const s = SITUATIONS.find((x) => x.key === key) ?? null;
    setSituation(s);
    if (s?.religious) setReligious(true);
  }, []);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    start(text.trim(), { religiousPath: religious });
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
      <label htmlFor="story" className="sr-only">{t("home.describe")}</label>
      <textarea id="story" className="input min-h-48 resize-y" required minLength={10} autoFocus value={text}
        placeholder={situation ? t(`situations.${situation.key}.placeholder`) : t("start.placeholder")}
        onChange={(e) => setText(e.target.value)} />

      <label className="flex items-start gap-3 rounded-2xl border border-line bg-surface p-4 text-sm">
        <input type="checkbox" className="mt-0.5 h-5 w-5 shrink-0 accent-brand" checked={religious}
          onChange={(e) => setReligious(e.target.checked)} />
        <span>
          <span className="font-semibold">{t("start.religiousLabel")}</span>
          <span className="block text-muted">{t("start.religiousHint")} <Link href="/how-it-works#religious" className="link">{t("start.religiousMore")}</Link></span>
        </span>
      </label>

      {emergency && <EmergencyPanel info={emergency}
        onContinue={() => { dismissEmergency(); start(text.trim(), { skipTriage: true, religiousPath: religious }); }} />}
      {error && <Alert tone="danger" role="alert">{error}</Alert>}
      <Button size="lg" className="w-full sm:w-auto" disabled={busy || text.trim().length < 10}
        icon={busy ? "spinner" : undefined} iconEnd={busy ? undefined : "arrowRight"}>
        {busy ? t("start.busy") : t("start.submit")}
      </Button>
      <p className="text-xs text-muted">{t("start.country")} <Link href="/coverage" className="link">{t("start.otherCountry")}</Link></p>
      <p className="text-xs text-muted">{t("landing.disclaimer")}</p>
    </form>
  );
}
