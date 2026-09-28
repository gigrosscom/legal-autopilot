"use client";

import { CaseBoard } from "@/components/CaseBoard";
import { EmergencyPanel } from "@/components/EmergencyPanel";
import { LevelBadge, type Level } from "@/components/LevelBadge";
import { PathMap } from "@/components/PathMap";
import { StageProgress } from "@/components/StageProgress";
import { Alert, Badge, Button, Icon, Section, type IconName } from "@/components/ui";
import { useT } from "@/lib/i18n";

const COLORS = [
  ["ink", "bg-ink"], ["ink-soft", "bg-ink-soft"], ["muted", "bg-muted"], ["line", "bg-line"], ["sand", "bg-sand"],
  ["sand-deep", "bg-sand-deep"], ["surface", "bg-surface"], ["brand", "bg-brand"], ["brand-dark", "bg-brand-dark"],
  ["brand-50", "bg-brand-50"], ["danger", "bg-danger"], ["warning", "bg-warning"], ["info", "bg-info"], ["draft", "bg-draft"],
];
const ICONS: IconName[] = ["document", "building", "clock", "escalate", "lawyer", "shieldCheck", "lock", "chart", "map",
  "alert", "info", "phone", "check", "globe", "cart", "briefcase", "family", "receipt", "landmark", "handshake", "scroll",
  "home", "community", "coin", "upload", "download", "send", "mail", "hourglass"];

/** Living catalogue of tokens and components (Konsilier design system). */
export default function DesignSystem() {
  const t = useT();
  return (
    <div className="space-y-14">
      <header className="max-w-3xl space-y-3">
        <p className="eyebrow">Konsiliér AI</p>
        <h1 className="text-4xl font-semibold tracking-tight">{t("ds.title")}</h1>
        <p className="text-lg text-muted">{t("ds.lead")}</p>
      </header>

      <Section title={t("ds.colors")}>
        <ul className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">
          {COLORS.map(([name, cls]) => (
            <li key={name} className="card p-2">
              <div className={`h-14 rounded-xl border border-line ${cls}`} />
              <p className="mt-2 font-mono text-xs">{name}</p>
            </li>
          ))}
        </ul>
      </Section>

      <Section title={t("ds.type")}>
        <div className="card space-y-3">
          <p className="text-5xl font-semibold tracking-tight">Konsilier · Қазақша ә ғ қ ң ө ұ ү һ і</p>
          <p className="text-3xl font-semibold" dir="rtl" lang="ar">كونسيلير — من الشكوى إلى القرار</p>
          <p className="text-2xl font-semibold">Türkçe ğ ş ı İ ö ü ç · English · Русский</p>
          <p className="text-base">{t("home.sub")}</p>
          <p className="text-sm text-muted">{t("landing.disclaimer")}</p>
        </div>
      </Section>

      <Section title={t("ds.buttons")}>
        <div className="flex flex-wrap gap-3">
          <Button icon="document">{t("case.prepare")}</Button>
          <Button variant="secondary" icon="download">DOCX</Button>
          <Button variant="danger" icon="phone">112</Button>
          <Button disabled>{t("common.loading")}</Button>
          <Button size="lg" iconEnd="arrowRight">{t("home.cta")}</Button>
        </div>
      </Section>

      <Section title={t("ds.badges")}>
        <div className="flex flex-wrap gap-2">
          {(["verified", "scenario_draft", "universal", "lawyer", "soon"] as Level[]).map((l) => <LevelBadge key={l} level={l} />)}
          <Badge tone="danger" icon="alert">danger</Badge><Badge tone="info">info</Badge><Badge>neutral</Badge>
        </div>
      </Section>

      <Section title={t("ds.notices")} lead={t("ds.noticesLead")}>
        <div className="grid gap-4 lg:grid-cols-2">
          <EmergencyPanel info={{ message: t("emergency.sample"), numbers: [{ label: "112", number: "112" }, { label: "102", number: "102" }] }} />
          <Alert tone="warning" title={t("ack.false_report.title")}
            actions={<Button icon="check">{t("ack.false_report.button")}</Button>}>{t("ack.false_report.text")}</Alert>
          <Alert tone="info" title={t("case.uplTitle")}>{t("ds.uplSample")}</Alert>
          <Alert tone="draft" title={t("case.draftTitle")}>{t("ds.draftSample")}</Alert>
        </div>
      </Section>

      <Section title={t("ds.forms")}>
        <form className="card grid max-w-xl gap-3" onSubmit={(e) => e.preventDefault()}>
          <label className="text-sm">{t("home.describe")}<textarea className="input mt-1" rows={3} placeholder={t("start.placeholder")} /></label>
          <label className="text-sm">{t("case.answerPlaceholder")}<input className="input mt-1" /></label>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="h-5 w-5 accent-brand" />{t("ack.special_category.button")}</label>
        </form>
      </Section>

      <Section title={t("ds.progress")}><div className="card max-w-md"><StageProgress stage="action_ready" /></div></Section>
      <Section title={t("home.pathTitle")}><PathMap /></Section>

      <Section title={t("ds.board")}>
        <CaseBoard onlyNonEmptyOnMobile={false} cards={[
          { id: "1", href: "#", title: t("situations.fired.label"), stage: "intake", level: "universal", attention: t("board.attention.chooseForum") },
          { id: "2", href: "#", title: t("situations.cheated.label"), stage: "action_ready", level: "verified", tasks: [{ label: t("case.prepare"), done: true }] },
          { id: "3", href: "#", title: t("situations.crime.label"), stage: "handed_to_lawyer", level: "lawyer" },
          { id: "4", href: "#", title: t("situations.bank.label"), stage: "resolved", level: "verified" },
        ]} />
      </Section>

      <Section title={t("ds.icons")}>
        <ul className="grid grid-cols-4 gap-3 sm:grid-cols-8 lg:grid-cols-10">
          {ICONS.map((n) => (
            <li key={n} className="card flex flex-col items-center gap-1 p-3"><Icon name={n} size={24} /><span className="font-mono text-[10px] text-muted">{n}</span></li>
          ))}
        </ul>
      </Section>
    </div>
  );
}
