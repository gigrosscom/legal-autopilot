"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { CtaBanner } from "@/components/CtaBanner";
import { Icon } from "@/components/ui";
import { useT } from "@/lib/i18n";
import { SITUATIONS } from "@/lib/situations";

function SectionHead({ title, lead, href, more }: { title: string; lead?: string; href?: string; more?: string }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3">
      <div className="max-w-2xl space-y-1.5">
        <h2 className="text-2xl font-semibold tracking-tight text-balance md:text-[28px]">{title}</h2>
        {lead && <p className="text-muted text-pretty">{lead}</p>}
      </div>
      {href && more && (
        <Link href={href} className="inline-flex min-h-11 items-center gap-2 text-sm font-medium text-brand hover:text-ink">
          {more}<Icon name="arrowRight" size={16} className="rtl:-scale-x-100" />
        </Link>
      )}
    </div>
  );
}

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
    <div className="space-y-16 md:space-y-20">
      {/* HERO: one main action — describe the situation */}
      <section className="grid items-center gap-8 pt-2 lg:grid-cols-[1.05fr_1fr] lg:gap-14 lg:pt-6">
        <div className="space-y-5">
          <p className="eyebrow">{t("home.eyebrow")}</p>
          <h1 className="text-[40px] font-semibold leading-[1.07] tracking-[-0.028em] text-ink text-balance md:text-[56px]">{t("home.title")}</h1>
          <p className="max-w-xl text-lg leading-relaxed text-muted text-pretty">{t("home.sub")}</p>
          <ul className="grid gap-2 pt-1 text-[15px] text-ink-soft sm:grid-cols-2">
            {(["promise1", "promise2", "promise3", "promise4"] as const).map((k) => (
              <li key={k} className="flex items-start gap-2.5">
                <Icon name="check" size={18} className="mt-0.5 text-brand" /><span>{t(`home.${k}`)}</span>
              </li>
            ))}
          </ul>
        </div>

        <form onSubmit={submit} aria-labelledby="describe"
          className="space-y-3 rounded-3xl border border-line bg-surface p-3 shadow-[var(--shadow-raised)] focus-within:border-accent">
          <label id="describe" htmlFor="story" className="block px-2 pt-2 text-base font-semibold text-ink">{t("home.describe")}</label>
          <textarea id="story" className="block min-h-40 w-full resize-y border-0 bg-transparent px-2 text-base leading-relaxed text-ink outline-none placeholder:text-faint"
            required minLength={10} value={text} onChange={(e) => setText(e.target.value)} placeholder={t("start.placeholder")} />
          <div className="flex items-center justify-between gap-3 border-t border-line px-2 pt-3">
            <span className="flex items-center gap-1.5 text-xs text-muted"><Icon name="globe" size={16} />{t("start.country").replace(/\.$/, "")}</span>
            <button type="submit" disabled={busy || text.trim().length < 10}
              className="btn-primary min-h-12 rounded-xl px-5 text-[15px]">
              {busy ? <Icon name="spinner" size={18} /> : null}{busy ? t("start.busy") : t("home.cta")}
              {!busy && <Icon name="arrowRight" size={18} className="rtl:-scale-x-100" />}
            </button>
          </div>
          <p className="px-2 pb-1 text-xs leading-relaxed text-muted">
            {t("home.privacy")} {t("legal.accept")} <Link href="/terms" className="link">{t("legal.terms")}</Link>
          </p>
        </form>
      </section>

      {/* LIFE SITUATIONS */}
      <section id="situations" className="scroll-mt-24 space-y-6 border-t border-line pt-12">
        <SectionHead title={t("home.situationsTitle")} lead={t("home.situationsLead")} href="/coverage" more={t("home.coverageCta")} />
        <ul className="grid grid-cols-2 gap-2.5 md:grid-cols-3 lg:grid-cols-4">
          {SITUATIONS.map((s) => (
            <li key={s.key}>
              <Link href={`/start?s=${s.key}`}
                className="flex h-full min-h-32 flex-col gap-3 rounded-2xl border border-transparent bg-sand p-4 transition-colors hover:border-line hover:bg-surface">
                <Icon name={s.icon} size={22} className="text-ink" />
                <span className="space-y-1">
                  <span className="block text-[15px] font-medium leading-snug text-ink">{t(`situations.${s.key}.label`)}</span>
                  <span className="line-clamp-2 block text-xs leading-relaxed text-muted">{t(`situations.${s.key}.hint`)}</span>
                </span>
              </Link>
            </li>
          ))}
          <li className="col-span-2">
            <Link href="/start"
              className="flex h-full min-h-32 items-center gap-4 rounded-2xl border border-line bg-surface p-4 transition-colors hover:border-accent">
              <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-ink text-white"><Icon name="plus" /></span>
              <span className="min-w-0 flex-1">
                <span className="block text-[15px] font-medium text-ink">{t("home.mySituation")}</span>
                <span className="block text-sm text-muted">{t("home.mySituationText")}</span>
              </span>
              <Icon name="arrowRight" className="shrink-0 text-muted rtl:-scale-x-100" />
            </Link>
          </li>
        </ul>
      </section>

      {/* FROM A QUESTION TO THE NEXT STEP */}
      <section className="space-y-8 border-t border-line pt-12">
        <SectionHead title={t("home.stepsTitle")} href="/how-it-works" more={t("home.more")} />
        <ol className="grid gap-8 md:grid-cols-3 md:gap-6">
          {([1, 2, 3] as const).map((n) => (
            <li key={n} className="relative space-y-3">
              <div className="flex items-center gap-3">
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-line bg-sand text-sm font-medium text-ink">{n}</span>
                {n < 3 && <span aria-hidden className="hidden h-px flex-1 bg-line md:block" />}
              </div>
              <p className="font-semibold text-ink">{t(`home.steps.s${n}t`)}</p>
              <p className="text-sm leading-relaxed text-muted">{t(`home.steps.s${n}d`)}</p>
            </li>
          ))}
        </ol>
      </section>

      {/* WHAT IT COSTS: three ways to get help, the lawyer card is the dark one */}
      <section className="space-y-6 border-t border-line pt-12">
        <SectionHead title={t("home.priceTitle")} />
        <ul className="grid gap-3 md:grid-cols-3">
          {([["chat", "chat", "/start"], ["doc", "document", "/start"], ["lawyer", "user", "/lawyers"]] as const).map(([k, icon, href]) => {
            const dark = k === "lawyer";
            return (
              <li key={k}>
                <Link href={href} className={`flex h-full flex-col gap-3 rounded-2xl border p-6 transition-colors ${dark ? "border-ink bg-ink text-white hover:bg-brand" : "border-line bg-surface hover:border-accent"}`}>
                  <Icon name={icon} size={22} className={dark ? "text-white" : "text-ink"} />
                  <span className={`text-lg font-semibold ${dark ? "text-white" : "text-ink"}`}>{t(`home.price.${k}T`)}</span>
                  <span className={`text-2xl font-semibold tracking-tight ${dark ? "text-white" : "text-ink"}`}>{t(`home.price.${k}P`)}</span>
                  <span className={`flex-1 text-sm leading-relaxed ${dark ? "text-white/75" : "text-muted"}`}>{t(`home.price.${k}D`)}</span>
                  <Icon name="arrowRight" size={18} className={`rtl:-scale-x-100 ${dark ? "text-white" : "text-ink"}`} />
                </Link>
              </li>
            );
          })}
        </ul>
      </section>

      {/* TRUST: only what is true today */}
      <section className="space-y-6 border-t border-line pt-12">
        <SectionHead title={t("home.trustTitle")} />
        <ul className="grid gap-6 md:grid-cols-3">
          {(["t1", "t2", "t3"] as const).map((k, i) => (
            <li key={k} className="flex gap-3 text-sm leading-relaxed text-muted">
              <Icon name={(["scroll", "lock", "shieldCheck"] as const)[i]} size={22} className="mt-0.5 shrink-0 text-ink" />
              <span>{t(`home.trust.${k}`)}</span>
            </li>
          ))}
        </ul>
      </section>

      <CtaBanner />

      {/* COVERAGE */}
      <section className="flex flex-col items-start gap-3 border-t border-line pt-10 md:flex-row md:items-center md:justify-between">
        <div className="space-y-1">
          <h2 className="text-lg font-semibold">{t("home.coverageTitle")}</h2>
          <p className="text-sm text-muted">{t("home.coverageLead")}</p>
        </div>
        <Link href="/coverage" className="btn-ghost">{t("home.coverageCta")}</Link>
      </section>
    </div>
  );
}
