"use client";

import Link from "next/link";
import { useState } from "react";
import { CtaBanner } from "@/components/CtaBanner";
import { Button, Icon, Section } from "@/components/ui";
import { useT } from "@/lib/i18n";
import { SITUATIONS } from "@/lib/situations";
import { useRouter } from "next/navigation";

export default function Home() {
  const t = useT();
  const [text, setText] = useState("");
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  // The story goes to the consultation chat, which checks for emergencies and opens the case.
  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (text.trim().length < 10) return;
    setBusy(true);
    try { sessionStorage.setItem("konsilier.chat.draft", text.trim()); } catch {}
    router.push("/start?send=1");
  }

  return (
    <div className="space-y-20">
      {/* HERO: the main action is a free text field, not a menu */}
      {/* phones: heading → form → promises; desktop: heading + promises | form */}
      <section className="grid gap-6 lg:grid-cols-[1.15fr_1fr] lg:gap-x-10 lg:gap-y-6">
        <div className="space-y-5 lg:self-end">
          <p className="eyebrow">{t("home.eyebrow")}</p>
          <h1 className="text-4xl font-bold leading-[1.1] tracking-tight text-balance md:text-5xl">{t("home.title")}</h1>
          <p className="max-w-xl text-lg text-muted text-pretty">{t("home.sub")}</p>
        </div>
        <ul className="order-3 grid gap-2 self-start text-sm sm:grid-cols-2 lg:order-none lg:col-start-1 lg:row-start-2">
            {(["promise1", "promise2", "promise3", "promise4"] as const).map((k) => (
              <li key={k} className="flex items-start gap-2">
                <Icon name="checkCircle" size={18} className="mt-0.5 text-brand" />
                <span>{t(`home.${k}`)}</span>
              </li>
            ))}
        </ul>

        <form onSubmit={submit} aria-labelledby="describe"
          className="card space-y-4 p-5 shadow-[var(--shadow-raised)] md:p-6 lg:col-start-2 lg:row-span-2 lg:row-start-1 lg:self-center">
          <label id="describe" htmlFor="story" className="block text-lg font-semibold">{t("home.describe")}</label>
          <textarea id="story" className="input min-h-44 resize-y" required minLength={10} value={text}
            onChange={(e) => setText(e.target.value)} placeholder={t("start.placeholder")} />
          <Button size="lg" className="w-full" disabled={busy || text.trim().length < 10} iconEnd={busy ? undefined : "arrowRight"}
            icon={busy ? "spinner" : undefined}>
            {busy ? t("start.busy") : t("home.cta")}
          </Button>
          <p className="text-xs text-muted">{t("home.privacy")}</p>
        </form>
      </section>

      {/* LIFE SITUATIONS */}
      <Section id="situations" className="scroll-mt-24" eyebrow={t("home.situationsEyebrow")} title={t("home.situationsTitle")} lead={t("home.situationsLead")}>
        <ul className="grid grid-cols-1 gap-3 min-[360px]:grid-cols-2 sm:grid-cols-3 lg:grid-cols-4">
          {SITUATIONS.map((s) => (
            <li key={s.key}>
              <Link href={`/start?s=${s.key}`}
                className="card flex h-full min-h-20 flex-col items-start gap-2 p-3 transition-shadow hover:shadow-[var(--shadow-raised)] sm:flex-row sm:gap-3 sm:p-4">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand sm:h-10 sm:w-10">
                  <Icon name={s.icon} />
                </span>
                <span className="min-w-0 break-words text-sm font-semibold leading-snug">{t(`situations.${s.key}.label`)}</span>
              </Link>
            </li>
          ))}
          {/* not in the list — describe your own; spans two columns so the last row is always full */}
          <li className="col-span-full min-[360px]:col-span-2">
            <Link href="/start"
              className="flex h-full min-h-20 items-center gap-3 rounded-2xl bg-brand p-3 text-white transition-shadow hover:bg-brand-dark hover:shadow-[var(--shadow-raised)] sm:p-4">
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-white/15 sm:h-10 sm:w-10">
                <Icon name="plus" />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block font-semibold leading-snug">{t("home.mySituation")}</span>
                <span className="block text-sm text-white/80">{t("home.mySituationText")}</span>
              </span>
              <Icon name="arrowRight" className="shrink-0 rtl:-scale-x-100" />
            </Link>
          </li>
        </ul>
      </Section>

      {/* HOW IT WORKS: three steps in plain words */}
      <Section title={t("home.stepsTitle")}>
        <ol className="grid gap-3 md:grid-cols-3">
          {([1, 2, 3] as const).map((n) => (
            <li key={n} className="card flex gap-4">
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-brand text-lg font-bold text-white">{n}</span>
              <span className="space-y-1">
                <span className="block font-semibold leading-snug">{t(`home.steps.s${n}t`)}</span>
                <span className="block text-sm text-muted">{t(`home.steps.s${n}d`)}</span>
              </span>
            </li>
          ))}
        </ol>
        <Link href="/how-it-works" className="link inline-flex items-center gap-1 text-sm font-medium">
          {t("home.more")}<Icon name="arrowRight" size={14} className="rtl:-scale-x-100" />
        </Link>
      </Section>

      {/* PRICES */}
      <Section title={t("home.priceTitle")}>
        <ul className="grid gap-3 md:grid-cols-3">
          {([["chat", "sparkle", "/start"], ["doc", "document", "/start"], ["lawyer", "lawyer", "/lawyers"]] as const).map(([k, icon, href]) => (
            <li key={k}>
              <Link href={href} className={`card flex h-full flex-col gap-2 transition-shadow hover:shadow-[var(--shadow-raised)] ${k === "chat" ? "border-brand" : ""}`}>
                <span className="flex items-center gap-2 font-semibold"><Icon name={icon} className="text-brand" />{t(`home.price.${k}T`)}</span>
                <span className="text-2xl font-bold text-brand">{t(`home.price.${k}P`)}</span>
                <span className="text-sm text-muted">{t(`home.price.${k}D`)}</span>
              </Link>
            </li>
          ))}
        </ul>
      </Section>

      {/* TRUST: only what is true today */}
      <Section title={t("home.trustTitle")}>
        <ul className="grid gap-3 md:grid-cols-3">
          {(["t1", "t2", "t3"] as const).map((k, i) => (
            <li key={k} className="flex gap-3 text-sm">
              <Icon name={(["scroll", "lock", "user"] as const)[i]} size={22} className="mt-0.5 shrink-0 text-brand" />
              <span>{t(`home.trust.${k}`)}</span>
            </li>
          ))}
        </ul>
      </Section>

      <CtaBanner />

      {/* COVERAGE TEASER */}
      <section className="card flex flex-col items-start gap-4 bg-ink p-6 text-white md:flex-row md:items-center md:justify-between md:p-8">
        <div className="space-y-1">
          <h2 className="text-xl font-bold">{t("home.coverageTitle")}</h2>
          <p className="text-white/80">{t("home.coverageLead")}</p>
        </div>
        <Link href="/coverage" className="btn bg-white text-ink hover:bg-sand">{t("home.coverageCta")}</Link>
      </section>
    </div>
  );
}
