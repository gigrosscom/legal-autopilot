"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Icon } from "@/components/ui";
import { LANGS, useLang, useT, type Lang } from "@/lib/i18n";

const NAV = [
  { href: "/how-it-works", key: "nav.howItWorks" },
  { href: "/coverage", key: "nav.coverage" },
  { href: "/lawyers", key: "nav.lawyers" },
  { href: "/for-lawyers", key: "nav.forLawyers" },
  { href: "/cases", key: "nav.cases" },
];

function LangSelect() {
  const t = useT();
  const { lang, setLang } = useLang();
  return (
    <label className="relative inline-flex items-center" title={LANGS.find((l) => l.code === lang)?.name}>
      <span className="sr-only">{t("nav.language")}</span>
      <Icon name="globe" size={16} className="pointer-events-none absolute start-2.5 text-muted" />
      <select value={lang} onChange={(e) => setLang(e.target.value as Lang)}
        className="min-h-10 appearance-none rounded-xl border border-line bg-surface ps-8 pe-3 text-sm font-medium">
        {LANGS.map((l) => <option key={l.code} value={l.code} lang={l.code}>{l.short}</option>)}
      </select>
    </label>
  );
}

export default function Header() {
  const t = useT();
  const path = usePathname();
  const active = (href: string) => (path === href || path.startsWith(href + "/") ? "text-ink" : "text-muted");
  return (
    <header className="sticky top-0 z-30 border-b border-line bg-sand/95">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:start-4 focus:top-2 focus:z-50 focus:rounded-lg focus:bg-surface focus:px-3 focus:py-2">
        {t("nav.skip")}
      </a>
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-4 py-2.5">
        <Link href="/" className="flex min-h-11 items-center text-lg font-bold tracking-tight" dir="ltr">
          Konsilier<span className="text-brand">.AI</span>
        </Link>
        <nav aria-label={t("nav.main")} className="hidden items-center gap-5 text-sm font-medium lg:flex">
          {NAV.map((n) => (
            <Link key={n.href} href={n.href} className={`py-2 hover:text-ink ${active(n.href)}`}>{t(n.key)}</Link>
          ))}
        </nav>
        <div className="flex items-center gap-2">
          <LangSelect />
          <Link href="/start" className="btn-primary hidden sm:inline-flex">{t("nav.start")}</Link>
          <details className="relative lg:hidden">
            <summary className="flex min-h-10 cursor-pointer list-none items-center rounded-xl border border-line bg-surface px-3 [&::-webkit-details-marker]:hidden">
              <span className="sr-only">{t("nav.menu")}</span>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden><path d="M4 7h16M4 12h16M4 17h16" /></svg>
            </summary>
            <nav aria-label={t("nav.main")}
              className="absolute end-0 top-12 z-40 flex w-60 flex-col rounded-2xl border border-line bg-surface p-2 shadow-[var(--shadow-raised)]">
              <Link href="/start" className="rounded-xl px-3 py-3 font-semibold text-brand hover:bg-sand">{t("nav.start")}</Link>
              {NAV.map((n) => (
                <Link key={n.href} href={n.href} className="rounded-xl px-3 py-3 hover:bg-sand">{t(n.key)}</Link>
              ))}
            </nav>
          </details>
        </div>
      </div>
    </header>
  );
}
