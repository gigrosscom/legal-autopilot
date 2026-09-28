"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { CtaBanner } from "@/components/CtaBanner";
import { Icon } from "@/components/ui";
import { useT } from "@/lib/i18n";
import { SITUATIONS } from "@/lib/situations";

/** apple.com-style link: blue text with a chevron, «Подробнее ›». */
function MoreLink({ href, children }: { href: string; children: string }) {
  return (
    <Link href={href} className="inline-flex min-h-11 items-center gap-1 text-[17px] text-brand hover:underline md:text-[19px]">
      {children}<Icon name="chevronDown" size={16} className="-rotate-90 rtl:rotate-90" />
    </Link>
  );
}

/** Centred section head: 32–48 px headline, 17–21 px lead, optional «more» link. */
function SectionHead({ title, lead, href, more }: { title: string; lead?: string; href?: string; more?: string }) {
  return (
    <div className="mx-auto max-w-3xl space-y-3 text-center">
      <h2 className="text-[32px] font-semibold leading-[1.08] tracking-[-0.015em] text-balance text-ink md:text-[48px]">{title}</h2>
      {lead && <p className="text-[17px] text-muted text-pretty md:text-[21px] md:leading-[1.38]">{lead}</p>}
      {href && more && <MoreLink href={href}>{more}</MoreLink>}
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
    <div className="space-y-4 md:space-y-5">
      {/* HERO: centred, large type, one main action — describe the situation */}
      <section className="mx-auto max-w-4xl space-y-6 pt-6 pb-10 text-center md:pt-10 md:pb-16">
        <p className="eyebrow">{t("home.eyebrow")}</p>
        <h1 className="mx-auto text-[length:var(--text-hero)] font-semibold leading-[1.05] tracking-[-0.015em] text-balance text-ink">{t("home.title")}</h1>
        <p className="mx-auto max-w-2xl text-[21px] leading-[1.38] text-muted text-pretty md:text-[28px] md:leading-[1.25] md:tracking-[-0.01em]">{t("home.sub")}</p>

        <form onSubmit={submit} aria-labelledby="describe"
          className="mx-auto mt-10 max-w-2xl space-y-3 rounded-3xl bg-surface p-3 text-start shadow-[var(--shadow-raised)] ring-1 ring-black/[0.06] transition-shadow focus-within:ring-2 focus-within:ring-action/40">
          <label id="describe" htmlFor="story" className="block px-3 pt-3 text-[17px] font-semibold text-ink">{t("home.describe")}</label>
          <textarea id="story" className="block min-h-36 w-full resize-y border-0 bg-transparent px-3 text-[17px] leading-[1.47] text-ink outline-none placeholder:text-faint"
            required minLength={10} value={text} onChange={(e) => setText(e.target.value)} placeholder={t("start.placeholder")} />
          <div className="flex flex-wrap items-center justify-between gap-3 px-2 pt-1">
            <span className="flex items-center gap-1.5 px-1 text-xs text-muted"><Icon name="globe" size={16} />{t("start.country").replace(/\.$/, "")}</span>
            <button type="submit" disabled={busy || text.trim().length < 10}
              className="btn-primary min-h-11 px-5 text-[15px]">
              {busy ? <Icon name="spinner" size={18} /> : null}{busy ? t("start.busy") : t("home.cta")}
              {!busy && <Icon name="arrowRight" size={16} className="rtl:-scale-x-100" />}
            </button>
          </div>
          <p className="px-3 pb-2 text-xs leading-relaxed text-muted">
            {t("home.privacy")} {t("legal.accept")} <Link href="/terms" className="link">{t("legal.terms")}</Link>
          </p>
        </form>

        <ul className="mx-auto grid max-w-3xl gap-x-8 gap-y-3 pt-6 text-start text-[15px] text-ink sm:grid-cols-2">
          {(["promise1", "promise2", "promise3", "promise4"] as const).map((k) => (
            <li key={k} className="flex items-start gap-2.5">
              <Icon name="checkCircle" size={20} className="mt-0.5 shrink-0 text-action" /><span>{t(`home.${k}`)}</span>
            </li>
          ))}
        </ul>
      </section>

      {/* LIFE SITUATIONS: grey tile with white cards */}
      <section id="situations" className="tile scroll-mt-20 space-y-10">
        <SectionHead title={t("home.situationsTitle")} lead={t("home.situationsLead")} href="/coverage" more={t("home.coverageCta")} />
        <ul className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-4">
          {SITUATIONS.map((s) => (
            <li key={s.key}>
              <Link href={`/start?s=${s.key}`}
                className="flex h-full min-h-36 flex-col gap-4 rounded-2xl bg-surface p-5 transition-[box-shadow,transform] hover:shadow-[var(--shadow-raised)] motion-safe:hover:-translate-y-0.5">
                <Icon name={s.icon} size={26} className="text-ink" />
                <span className="space-y-1">
                  <span className="block text-[17px] font-semibold leading-snug text-ink">{t(`situations.${s.key}.label`)}</span>
                  <span className="line-clamp-2 block text-sm leading-[1.43] text-muted">{t(`situations.${s.key}.hint`)}</span>
                </span>
              </Link>
            </li>
          ))}
          <li className="col-span-2">
            <Link href="/start"
              className="flex h-full min-h-36 items-center gap-4 rounded-2xl bg-ink p-5 text-white transition-opacity hover:opacity-90">
              <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-action text-white"><Icon name="plus" /></span>
              <span className="min-w-0 flex-1">
                <span className="block text-[17px] font-semibold">{t("home.mySituation")}</span>
                <span className="block text-sm text-white/75">{t("home.mySituationText")}</span>
              </span>
              <Icon name="chevronDown" className="shrink-0 -rotate-90 text-white/80 rtl:rotate-90" />
            </Link>
          </li>
        </ul>
      </section>

      {/* FROM A QUESTION TO THE NEXT STEP */}
      <section className="space-y-12 px-2 py-16 md:py-24">
        <SectionHead title={t("home.stepsTitle")} href="/how-it-works" more={t("home.more")} />
        <ol className="grid gap-10 md:grid-cols-3 md:gap-8">
          {([1, 2, 3] as const).map((n) => (
            <li key={n} className="space-y-3 text-center">
              <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-sand text-[21px] font-semibold text-ink">{n}</span>
              <p className="text-[21px] font-semibold leading-snug tracking-[-0.01em] text-ink">{t(`home.steps.s${n}t`)}</p>
              <p className="mx-auto max-w-xs text-[17px] text-muted">{t(`home.steps.s${n}d`)}</p>
            </li>
          ))}
        </ol>
      </section>

      {/* WHAT IT COSTS: three ways to get help, the lawyer card is the dark one */}
      <section className="tile space-y-10">
        <SectionHead title={t("home.priceTitle")} />
        <ul className="grid gap-3 md:grid-cols-3">
          {([["chat", "chat", "/start"], ["doc", "document", "/start"], ["lawyer", "user", "/lawyers"]] as const).map(([k, icon, href]) => {
            const dark = k === "lawyer";
            return (
              <li key={k}>
                <Link href={href} className={`flex h-full flex-col gap-3 rounded-2xl p-7 transition-shadow hover:shadow-[var(--shadow-raised)] ${dark ? "bg-ink text-white" : "bg-surface"}`}>
                  <Icon name={icon} size={28} className={dark ? "text-white" : "text-ink"} />
                  <span className={`pt-2 text-[21px] font-semibold ${dark ? "text-white" : "text-ink"}`}>{t(`home.price.${k}T`)}</span>
                  <span className={`text-[32px] font-semibold leading-tight tracking-[-0.015em] ${dark ? "text-white" : "text-ink"}`}>{t(`home.price.${k}P`)}</span>
                  <span className={`flex-1 text-[15px] leading-relaxed ${dark ? "text-white/75" : "text-muted"}`}>{t(`home.price.${k}D`)}</span>
                  <span className={`inline-flex items-center gap-1 text-[15px] ${dark ? "text-[#2997ff]" : "text-brand"}`}>
                    {t("home.more")}<Icon name="chevronDown" size={14} className="-rotate-90 rtl:rotate-90" />
                  </span>
                </Link>
              </li>
            );
          })}
        </ul>
      </section>

      {/* TRUST: only what is true today */}
      <section className="space-y-12 px-2 py-16 md:py-24">
        <SectionHead title={t("home.trustTitle")} />
        <ul className="grid gap-10 md:grid-cols-3 md:gap-8">
          {(["t1", "t2", "t3"] as const).map((k, i) => (
            <li key={k} className="space-y-4 text-center">
              <Icon name={(["scroll", "lock", "shieldCheck"] as const)[i]} size={36} strokeWidth={1.4} className="mx-auto text-ink" />
              <p className="mx-auto max-w-xs text-[17px] text-muted">{t(`home.trust.${k}`)}</p>
            </li>
          ))}
        </ul>
      </section>

      <CtaBanner />

      {/* COVERAGE */}
      <section className="flex flex-col items-center gap-2 px-2 py-14 text-center">
        <h2 className="text-[21px] font-semibold tracking-[-0.01em] text-ink md:text-[28px]">{t("home.coverageTitle")}</h2>
        <p className="max-w-2xl text-[17px] text-muted">{t("home.coverageLead")}</p>
        <MoreLink href="/coverage">{t("home.coverageCta")}</MoreLink>
      </section>
    </div>
  );
}
