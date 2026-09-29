"use client";

import { CtaBanner } from "@/components/CtaBanner";
import { LevelAction, LevelBadge } from "@/components/LevelBadge";
import { PathMap } from "@/components/PathMap";
import { Alert, Button, Icon, Section, type IconName } from "@/components/ui";
import { LAWYERS_PUBLIC } from "@/lib/features";
import { useT } from "@/lib/i18n";

const LEVELS = ["verified", "universal", "lawyer"] as const;

function List({ prefix, n, icon, iconClass = "text-brand" }: { prefix: string; n: number; icon: IconName; iconClass?: string }) {
  const t = useT();
  return (
    <ul className="space-y-2">
      {Array.from({ length: n }, (_, i) => (
        <li key={i} className="flex gap-2 text-sm"><Icon name={icon} size={18} className={`mt-0.5 ${iconClass}`} /><span>{t(`${prefix}.${i + 1}`)}</span></li>
      ))}
    </ul>
  );
}

export default function HowItWorks() {
  const t = useT();
  return (
    <div className="space-y-16">
      <header className="max-w-3xl space-y-3">
        <p className="eyebrow">{t("how.eyebrow")}</p>
        <h1 className="text-4xl font-semibold tracking-tight text-balance">{t("how.title")}</h1>
        <p className="text-lg text-muted">{t("how.lead")}</p>
      </header>

      <Section title={t("how.pathTitle")} lead={t("how.pathLead")}>
        <PathMap />
        <Button href="/start" iconEnd="arrowRight">{t("cta.startCase")}</Button>
      </Section>

      <Section title={t("how.levelsTitle")} lead={t("how.levelsLead")}>
        <div className="grid gap-4 lg:grid-cols-3">
          {LEVELS.map((lv) => (
            <article key={lv} className="card flex flex-col items-start gap-3">
              <LevelBadge level={lv} />
              <h3 className="text-lg font-semibold">{t(`how.level.${lv}.title`)}</h3>
              <p className="text-sm text-muted">{t(`how.level.${lv}.when`)}</p>
              <List prefix={`how.level.${lv}.get`} n={3} icon="check" />
              <LevelAction level={lv} />
            </article>
          ))}
        </div>
      </Section>

      <Section title={t("how.rolesTitle")}>
        <div className="grid gap-4 md:grid-cols-2">
          <div className="card space-y-3">
            <h3 className="flex items-center gap-2 font-semibold"><Icon name="document" className="text-brand" />{t("how.ai.title")}</h3>
            <List prefix="how.ai.does" n={4} icon="check" />
            <p className="pt-1 text-sm font-semibold">{t("how.ai.neverTitle")}</p>
            <List prefix="how.ai.never" n={4} icon="x" iconClass="text-danger" />
          </div>
          <div className="card space-y-3">
            <h3 className="flex items-center gap-2 font-semibold"><Icon name="lawyer" className="text-brand" />{t("how.lawyer.title")}</h3>
            <List prefix="how.lawyer.does" n={4} icon="check" />
            {LAWYERS_PUBLIC && <div className="flex flex-wrap gap-2 pt-1">
              <Button href="/lawyers" icon="lawyer">{t("cta.lawyer")}</Button>
              <Button href="/for-lawyers" variant="secondary">{t("cta.join")}</Button>
            </div>}
          </div>
        </div>
      </Section>

      <Section title={t("how.promiseTitle")} lead={t("how.promiseLead")}>
        <div className="grid gap-4 md:grid-cols-2">
          <div className="card space-y-3">
            <h3 className="font-semibold">{t("how.promise.title")}</h3>
            <List prefix="how.promise" n={4} icon="checkCircle" />
          </div>
          <div className="card space-y-3">
            <h3 className="font-semibold">{t("how.dont.title")}</h3>
            <List prefix="how.dont" n={4} icon="x" iconClass="text-danger" />
          </div>
        </div>
      </Section>

      <Section title={t("how.safetyTitle")}>
        <div className="grid gap-4 lg:grid-cols-3">
          <Alert tone="danger" icon="phone" title={t("how.safety.emergency.title")}>{t("how.safety.emergency.text")}</Alert>
          <Alert tone="warning" title={t("how.safety.falseReport.title")}>{t("how.safety.falseReport.text")}</Alert>
          <Alert tone="info" icon="shield" title={t("how.safety.abuse.title")}>{t("how.safety.abuse.text")}</Alert>
        </div>
      </Section>

      <CtaBanner />
    </div>
  );
}
