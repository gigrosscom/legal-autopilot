"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef } from "react";
import { Brand } from "@/components/Brand";
import { InstallApp } from "@/components/InstallApp";
import { Icon } from "@/components/ui";
import { LANGS, useLang, useT, type Lang } from "@/lib/i18n";

const NAV = [
  { href: "/how-it-works", key: "nav.howItWorks" },
  { href: "/coverage", key: "nav.coverage" },
  { href: "/lawyers", key: "nav.lawyers" },
  { href: "/for-lawyers", key: "nav.forLawyers" },
  { href: "/cases", key: "nav.cases" },
];

export function LangSelect() {
  const t = useT();
  const { lang, setLang } = useLang();
  return (
    <label className="relative inline-flex items-center" title={LANGS.find((l) => l.code === lang)?.name}>
      <span className="sr-only">{t("nav.language")}</span>
      <Icon name="globe" size={15} className="pointer-events-none absolute start-2.5 text-ink/80" />
      <select value={lang} onChange={(e) => setLang(e.target.value as Lang)}
        className="min-h-9 appearance-none rounded-full bg-transparent ps-8 pe-3 text-[13px] text-ink hover:bg-black/[0.04]">
        {LANGS.map((l) => <option key={l.code} value={l.code} lang={l.code}>{l.short}</option>)}
      </select>
    </label>
  );
}

export default function Header() {
  const t = useT();
  const path = usePathname();
  const menu = useRef<HTMLDetailsElement>(null);
  // the full-screen menu closes after navigation
  useEffect(() => { if (menu.current) menu.current.open = false; }, [path]);
  const active = (href: string) => (path === href || path.startsWith(href + "/") ? "text-ink" : "text-ink/80");
  return (
    // Apple-style global nav: 48 px, light, translucent with backdrop blur, hairline at the bottom
    <header className="sticky top-0 z-30 border-b border-black/[0.08] pt-[env(safe-area-inset-top)]">
      {/* The blur sits on its own layer: backdrop-filter on the header itself would trap the fixed full-screen menu. */}
      <div aria-hidden className="absolute inset-0 -z-10 bg-[#fbfbfd]/80 backdrop-blur-xl backdrop-saturate-[1.8]" />
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:start-4 focus:top-2 focus:z-50 focus:rounded-lg focus:bg-surface focus:px-3 focus:py-2">
        {t("nav.skip")}
      </a>
      <div className="mx-auto flex h-12 max-w-[1120px] items-center justify-between gap-2 px-3 min-[360px]:gap-3 min-[360px]:px-5">
        <Link href="/" className="flex min-h-11 items-center" aria-label="Konsiliér AI">
          <Brand size={22} />
        </Link>
        <nav aria-label={t("nav.main")} className="hidden items-center gap-8 text-[13px] tracking-[-0.01em] lg:flex">
          {NAV.map((n) => (
            <Link key={n.href} href={n.href} className={`inline-flex min-h-11 items-center transition-colors hover:text-ink ${active(n.href)}`}>{t(n.key)}</Link>
          ))}
        </nav>
        <div className="flex items-center gap-1 min-[360px]:gap-1.5">
          {/* very narrow phones (Galaxy Fold): the language moves into the menu */}
          <div className="max-[359px]:hidden"><LangSelect /></div>
          <Link href="/account" aria-label={t("nav.account")} title={t("nav.account")}
            className={`flex min-h-9 items-center gap-1.5 rounded-full px-2.5 text-[13px] hover:bg-black/[0.04] ${active("/account")}`}>
            <Icon name="user" size={16} /><span className="hidden md:inline">{t("nav.account")}</span>
          </Link>
          <Link href="/start" className="btn-primary hidden min-h-8 px-3.5 py-1 text-[13px] sm:inline-flex">{t("nav.start")}</Link>
          {/* phone / tablet: Apple-style full-screen menu with large links */}
          <details ref={menu} className="group lg:hidden">
            <summary className="flex min-h-11 min-w-11 cursor-pointer list-none items-center justify-center rounded-full hover:bg-black/[0.04] [&::-webkit-details-marker]:hidden">
              <span className="sr-only">{t("nav.menu")}</span>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" aria-hidden className="group-open:hidden"><path d="M5 9h14M5 15h14" /></svg>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" aria-hidden className="hidden group-open:block"><path d="m6 6 12 12M18 6 6 18" /></svg>
            </summary>
            <nav aria-label={t("nav.main")}
              className="fixed inset-x-0 top-[calc(3rem+env(safe-area-inset-top))] bottom-0 z-40 flex flex-col overflow-y-auto bg-[#fbfbfd]/95 px-8 pt-6 pb-10 backdrop-blur-xl sm:px-12">
              <div className="pb-4 min-[360px]:hidden"><LangSelect /></div>
              <Link href="/start" className="py-2 text-[28px] font-semibold leading-tight tracking-[-0.015em] text-brand">{t("nav.start")}</Link>
              {NAV.map((n) => (
                <Link key={n.href} href={n.href} className="py-2 text-[28px] font-semibold leading-tight tracking-[-0.015em] text-ink hover:text-brand">{t(n.key)}</Link>
              ))}
              <InstallApp className="mt-6 border-t border-black/[0.08] pt-6" />
            </nav>
          </details>
        </div>
      </div>
    </header>
  );
}
