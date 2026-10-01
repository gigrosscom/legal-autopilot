"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { Brand } from "@/components/Brand";
import { InstallApp } from "@/components/InstallApp";
import { Icon } from "@/components/ui";
import { api, SIGNED_IN_EVENT, type Me } from "@/lib/api";
import { LAWYERS_PUBLIC } from "@/lib/features";
import { LANGS, useLang, useT, type Lang } from "@/lib/i18n";

const NAV = [
  { href: "/how-it-works", key: "nav.howItWorks" },
  { href: "/coverage", key: "nav.coverage" },
  ...(LAWYERS_PUBLIC ? [{ href: "/lawyers", key: "nav.lawyers" }, { href: "/for-lawyers", key: "nav.forLawyers" }] : []),
  { href: "/cases", key: "nav.cases" },
  { href: "/app", key: "nav.app" },
];

/** The signed-in person's first name for the header (null while not signed in or unknown). */
function useAccountName(): string | null {
  const [name, setName] = useState<string | null>(null);
  useEffect(() => {
    const load = () => {
      let token: string | null = null;
      try { token = localStorage.getItem("konsilier.token"); } catch {}
      if (!token) { setName(null); return; }
      api<Me>("/v1/me").then((m) => {
        if (!m.identities.length) { setName(null); return; }
        setName((m.display_name || "").trim().split(/\s+/)[0] || "");
      }).catch(() => setName(null));
    };
    load();
    window.addEventListener(SIGNED_IN_EVENT, load);
    return () => window.removeEventListener(SIGNED_IN_EVENT, load);
  }, []);
  return name;
}

export function LangSelect() {
  const t = useT();
  const { lang, setLang } = useLang();
  return (
    <label className="relative inline-flex items-center" title={LANGS.find((l) => l.code === lang)?.name}>
      <span className="sr-only">{t("nav.language")}</span>
      <Icon name="globe" size={16} className="pointer-events-none absolute start-2.5 text-ink/80" />
      <select value={lang} onChange={(e) => setLang(e.target.value as Lang)}
        className="min-h-11 appearance-none rounded-full border-0 bg-transparent ps-8 pe-3 text-[12px] font-normal text-ink/80 hover:bg-ink/[0.05] hover:text-ink">
        {LANGS.map((l) => <option key={l.code} value={l.code} lang={l.code}>{l.short}</option>)}
      </select>
    </label>
  );
}

export default function Header() {
  const t = useT();
  const path = usePathname();
  // apple globalnav: 12 px links, rgba(0,0,0,.8) (here #1d1d1f at .8: 11:1 on the bar), full black when current/hover
  const name = useAccountName();
  const active = (href: string) => (path === href || path.startsWith(href + "/") ? "text-ink" : "text-ink/80");
  return (
    <header className="sticky top-0 z-30 bg-bar/92 pt-[env(safe-area-inset-top)] supports-[backdrop-filter]:bg-bar/80 supports-[backdrop-filter]:backdrop-blur-[20px] supports-[backdrop-filter]:backdrop-saturate-[1.8]">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:start-4 focus:top-2 focus:z-50 focus:rounded-lg focus:bg-surface focus:px-3 focus:py-2">
        {t("nav.skip")}
      </a>
      <div className="mx-auto flex h-12 max-w-[1208px] items-center justify-between gap-2 px-3 min-[360px]:gap-3 min-[360px]:px-5">
        <Link href="/" className="flex min-h-11 items-center" aria-label="Konsiliér AI">
          <Brand size={26} />
        </Link>
        <nav aria-label={t("nav.main")} className="hidden items-center gap-8 text-[12px] tracking-[-0.01em] lg:flex">
          {NAV.map((n) => (
            <Link key={n.href} href={n.href} className={`inline-flex min-h-11 items-center transition-colors hover:text-ink ${active(n.href)}`}>{t(n.key)}</Link>
          ))}
        </nav>
        <div className="flex items-center gap-1.5 min-[360px]:gap-2">
          {/* very narrow phones (Galaxy Fold): the language moves into the menu */}
          <div className="max-[359px]:hidden"><LangSelect /></div>
          {name !== null ? (
            <Link href="/account" aria-label={name || t("app.tabs.profile")} title={name || t("app.tabs.profile")}
              className={`flex min-h-11 min-w-11 items-center justify-center gap-1.5 rounded-full px-2.5 text-[12px] hover:bg-ink/[0.05] hover:text-ink ${active("/account")}`}>
              <span aria-hidden="true" className="flex h-6 w-6 items-center justify-center rounded-full bg-action text-[11px] font-semibold uppercase text-white">
                {name ? name[0] : <Icon name="user" size={14} />}</span>
              <span className="hidden max-w-[10rem] truncate md:inline">{name || t("app.tabs.profile")}</span>
            </Link>
          ) : (
          <Link href="/account?signin=1" aria-label={t("nav.account")} title={t("nav.account")}
            className={`flex min-h-11 min-w-11 items-center justify-center gap-1.5 rounded-full px-2.5 text-[12px] hover:bg-ink/[0.05] hover:text-ink ${active("/account")}`}>
            <Icon name="user" size={17} /><span className="hidden md:inline">{t("nav.account")}</span>
          </Link>
          )}
          <Link href="/start" className="btn-primary hidden min-h-8 px-3.5 py-1 text-[12px] tracking-[-0.01em] sm:inline-flex">{t("nav.start")}</Link>
          <details className="relative lg:hidden">
            <summary className="flex min-h-11 min-w-11 justify-center cursor-pointer list-none items-center rounded-full px-3 text-ink/80 hover:bg-ink/[0.05] [&::-webkit-details-marker]:hidden">
              <span className="sr-only">{t("nav.menu")}</span>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden><path d="M4 7h16M4 12h16M4 17h16" /></svg>
            </summary>
            <nav aria-label={t("nav.main")}
              onClick={(e) => { if ((e.target as HTMLElement).closest("a")) e.currentTarget.closest("details")?.removeAttribute("open"); }}
              className="absolute end-0 top-11 z-40 flex w-64 max-w-[calc(100vw-1.5rem)] flex-col rounded-[18px] bg-surface p-2 text-[17px] shadow-[0_12px_40px_rgb(0_0_0/0.14)]">
              <div className="px-1 pb-2 min-[360px]:hidden"><LangSelect /></div>
              <Link href="/start" className="rounded-xl px-3 py-3 font-semibold text-brand hover:bg-sand">{t("nav.start")}</Link>
              {NAV.map((n) => (
                <Link key={n.href} href={n.href} className="rounded-xl px-3 py-3 hover:bg-sand">{t(n.key)}</Link>
              ))}
              <InstallApp className="border-t border-ink/[0.08] px-1 pt-2" />
            </nav>
          </details>
        </div>
      </div>
    </header>
  );
}
