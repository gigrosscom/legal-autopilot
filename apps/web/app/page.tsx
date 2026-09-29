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
    <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
      <div className="max-w-3xl space-y-3">
        <h2 className="h-section text-balance">{title}</h2>
        {lead && <p className="lead text-pretty">{lead}</p>}
      </div>
      {href && more && (
        <Link href={href} className="more">
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
    <div>
      {/* HERO: one main action — describe the situation */}
      <section className="grid items-center gap-10 pt-4 pb-14 md:pt-8 md:pb-20 lg:grid-cols-[1.05fr_1fr] lg:gap-14 lg:pt-10 lg:pb-24">
        <div className="space-y-6">
          <p className="eyebrow">{t("home.eyebrow")}</p>
          <h1 className="h-hero text-ink text-balance">{t("home.title")}</h1>
          <p className="lead max-w-xl text-pretty">{t("home.sub")}</p>
          <ul className="grid gap-x-6 gap-y-3 pt-2 text-[17px] leading-snug text-ink sm:grid-cols-2">
            {(["promise1", "promise2", "promise3", "promise4"] as const).map((k) => (
              <li key={k} className="flex items-start gap-2.5">
                <Icon name="check" size={18} className="mt-0.5 shrink-0 text-brand" /><span>{t(`home.${k}`)}</span>
              </li>
            ))}
          </ul>
        </div>

        <form onSubmit={submit} aria-labelledby="describe"
          className="space-y-3 rounded-[28px] bg-sand p-4 ring-accent/40 transition-shadow focus-within:ring-2 md:p-5">
          <label id="describe" htmlFor="story" className="block px-2 pt-2 text-[19px] font-semibold tracking-[-0.01em] text-ink">{t("home.describe")}</label>
          <textarea id="story" className="block min-h-40 w-full resize-y rounded-[18px] border-0 bg-surface px-4 py-3 text-[17px] leading-relaxed text-ink outline-none placeholder:text-faint"
            required minLength={10} value={text} onChange={(e) => setText(e.target.value)} placeholder={t("start.placeholder")} />
          <div className="flex flex-wrap items-center justify-between gap-3 px-2 pt-1">
            <span className="flex min-w-0 items-center gap-1.5 text-sm text-muted"><Icon name="globe" size={16} className="shrink-0" />{t("start.country").replace(/\.$/, "")}</span>
            <button type="submit" disabled={busy || text.trim().length < 10}
              className="btn-primary btn-lg w-full px-5 sm:w-auto sm:whitespace-nowrap">
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
      <section id="situations" className="band section-y scroll-mt-12 space-y-10">
        <SectionHead title={t("home.situationsTitle")} lead={t("home.situationsLead")} href="/coverage" more={t("home.coverageCta")} />
        <ul className="grid grid-cols-2 gap-3 md:grid-cols-3 md:gap-4 lg:grid-cols-4">
          {SITUATIONS.map((s) => (
            <li key={s.key}>
              <Link href={`/start?s=${s.key}`}
                className="card-link flex h-full min-h-36 flex-col gap-4 rounded-[18px] bg-surface p-4 sm:p-5 md:p-6">
                <Icon name={s.icon} size={24} className="text-ink" />
                <span className="space-y-1">
                  <span className="block text-[15px] font-semibold leading-snug tracking-[-0.015em] text-ink sm:text-[17px]">{t(`situations.${s.key}.label`)}</span>
                  <span className="line-clamp-2 block text-[13px] leading-relaxed text-muted sm:text-sm">{t(`situations.${s.key}.hint`)}</span>
                </span>
              </Link>
            </li>
          ))}
          <li className="col-span-2">
            <Link href="/start"
              className="card-link flex h-full min-h-36 items-center gap-4 rounded-[18px] bg-surface p-5 md:p-6">
              <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-action text-white"><Icon name="plus" /></span>
              <span className="min-w-0 flex-1">
                <span className="block text-[17px] font-semibold tracking-[-0.015em] text-ink">{t("home.mySituation")}</span>
                <span className="block text-[15px] text-muted">{t("home.mySituationText")}</span>
              </span>
              <Icon name="arrowRight" className="shrink-0 text-muted rtl:-scale-x-100" />
            </Link>
          </li>
        </ul>
      </section>

      {/* FROM A QUESTION TO THE NEXT STEP */}
      <section className="section-y space-y-10 md:space-y-12">
        <SectionHead title={t("home.stepsTitle")} href="/how-it-works" more={t("home.more")} />
        <ol className="grid gap-8 md:grid-cols-3 md:gap-6">
          {([1, 2, 3] as const).map((n) => (
            <li key={n} className="relative space-y-3">
              <div className="flex items-center gap-3">
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-sand text-[17px] font-semibold text-ink">{n}</span>
                {n < 3 && <span aria-hidden className="hidden h-px flex-1 bg-line md:block" />}
              </div>
              <p className="text-[21px] font-semibold leading-snug tracking-[-0.015em] text-ink">{t(`home.steps.s${n}t`)}</p>
              <p className="text-[17px] leading-[1.47] text-muted">{t(`home.steps.s${n}d`)}</p>
            </li>
          ))}
        </ol>
      </section>

      {/* WHAT IT COSTS: three ways to get help, three equal cards */}
      <section className="band section-y space-y-10">
        <SectionHead title={t("home.priceTitle")} />
        <ul className="grid gap-4 md:grid-cols-3">
          {([["chat", "chat", "/start"], ["doc", "document", "/start"], ["lawyer", "user", "/lawyers"]] as const).map(([k, icon, href]) => (
              <li key={k}>
                <Link href={href} className="card-link flex h-full flex-col gap-3 rounded-[18px] bg-surface p-7 md:p-8">
                  <Icon name={icon} size={26} className="text-ink" />
                  <span className="text-[21px] font-semibold tracking-[-0.015em] text-ink">{t(`home.price.${k}T`)}</span>
                  <span className="text-[32px] leading-tight font-semibold tracking-[-0.02em] text-ink">{t(`home.price.${k}P`)}</span>
                  <span className="flex-1 text-[17px] leading-[1.47] text-muted">{t(`home.price.${k}D`)}</span>
                  <Icon name="arrowRight" size={20} className="text-brand rtl:-scale-x-100" />
                </Link>
              </li>
          ))}
        </ul>
      </section>

      {/* TRUST: only what is true today */}
      <section className="section-y space-y-10">
        <SectionHead title={t("home.trustTitle")} />
        <ul className="grid gap-4 md:grid-cols-3">
          {(["t1", "t2", "t3"] as const).map((k, i) => (
            <li key={k} className="card flex gap-4 text-[17px] leading-[1.47] text-muted">
              <Icon name={(["scroll", "lock", "shieldCheck"] as const)[i]} size={26} className="mt-0.5 shrink-0 text-ink" />
              <span>{t(`home.trust.${k}`)}</span>
            </li>
          ))}
        </ul>
      </section>

      <CtaBanner />

      {/* COVERAGE */}
      <section className="flex flex-col items-start gap-5 pt-14 pb-6 md:flex-row md:items-center md:justify-between md:pt-20">
        <div className="space-y-1">
          <h2 className="text-[24px] font-semibold leading-tight tracking-[-0.015em] md:text-[28px]">{t("home.coverageTitle")}</h2>
          <p className="text-[17px] text-muted">{t("home.coverageLead")}</p>
        </div>
        <Link href="/coverage" className="btn-ghost btn-lg">{t("home.coverageCta")}</Link>
      </section>
    </div>
  );
}
