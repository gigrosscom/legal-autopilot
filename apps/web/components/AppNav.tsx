"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { Brand } from "@/components/Brand";
import { LangSelect } from "@/components/Header";
import { NotificationBell } from "@/components/NotificationBell";
import { Icon, type IconName } from "@/components/ui";
import { api, isSignedIn, SIGNED_IN_EVENT, type CaseView } from "@/lib/api";
import { useT } from "@/lib/i18n";

/** Routes that are the app (not the website): they get the sidebar on desktop and the tab bar on phones. */
const APP_ROUTES = ["/start", "/chat", "/cases", "/case", "/documents", "/account", "/share"];
export const isAppRoute = (path: string) => APP_ROUTES.some((r) => path === r || path.startsWith(r + "/"));

export const LAST_CASE_KEY = "konsilier.lastCase";

type Tab = { key: string; href: string; icon: IconName; match: (p: string) => boolean };

/** false while this device is not signed in (the app then offers «Войти»); null until known. */
export function useSignedIn(): boolean | null {
  const [value, setValue] = useState<boolean | null>(null);
  useEffect(() => {
    const check = () => { isSignedIn().then(setValue); };
    check();
    window.addEventListener(SIGNED_IN_EVENT, check);
    return () => window.removeEventListener(SIGNED_IN_EVENT, check);
  }, []);
  return value;
}

function SignInLink({ className }: { className: string }) {
  const t = useT();
  return (
    <Link href="/account?signin=1" className={className} aria-label={t("app.signIn")}>
      <Icon name="login" size={18} /><span className="max-[359px]:sr-only">{t("app.signIn")}</span>
    </Link>
  );
}

function useTabs(): Tab[] {
  const [last, setLast] = useState<string | null>(null);
  useEffect(() => { try { setLast(localStorage.getItem(LAST_CASE_KEY)); } catch {} }, []);
  return [
    { key: "home", href: "/start", icon: "home", match: (p) => p === "/start" },
    { key: "chat", href: last ? `/chat/${last}` : "/start", icon: "chat", match: (p) => p.startsWith("/chat") },
    { key: "cases", href: "/cases", icon: "folder", match: (p) => p === "/cases" || p.startsWith("/case/") },
    { key: "documents", href: "/documents", icon: "document", match: (p) => p === "/documents" },
    { key: "profile", href: "/account", icon: "user", match: (p) => p === "/account" },
  ];
}

/** Phone tab bar: five sections, icon over label. `inline` renders it inside a full-screen layout. */
export function TabBar({ inline = false }: { inline?: boolean }) {
  const t = useT();
  const path = usePathname();
  const tabs = useTabs();
  const signed = useSignedIn();
  return (
    <nav aria-label={t("nav.main")}
      className={`${inline ? "" : "fixed inset-x-0 bottom-[var(--app-gap,0px)] z-30"} border-t border-line bg-surface pb-[env(safe-area-inset-bottom)] lg:hidden`}>
      <ul className="mx-auto grid max-w-lg grid-cols-5">
        {tabs.map((tab) => {
          const on = tab.match(path);
          return (
            <li key={tab.key}>
              <Link href={tab.href} aria-current={on ? "page" : undefined}
                className={`flex h-16 flex-col items-center justify-center gap-1 text-[11px] ${on ? "font-semibold text-ink" : "text-muted hover:text-ink"}`}>
                <Icon name={tab.icon} size={22} strokeWidth={on ? 2.1 : 1.6} />
                <span className="max-w-full truncate px-0.5">{t(tab.key === "profile" && signed === false ? "app.signIn" : `app.tabs.${tab.key}`)}</span>
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

/** Desktop sidebar: brand and notifications, «Новый вопрос», the five sections, recent cases, language and the way back to the site. */
export function Sidebar() {
  const t = useT();
  const path = usePathname();
  const tabs = useTabs();
  const signed = useSignedIn();
  const [cases, setCases] = useState<CaseView[]>([]);
  // once per page: the list only feeds the «recent cases» links
  useEffect(() => { api<CaseView[]>("/v1/cases").then(setCases).catch(() => {}); }, []);
  const recent = cases.slice(0, 5).map((c) => ({ id: c.id, title: c.scenario?.title ?? c.coverage?.dispute?.title ?? t("case.untitled") }));
  return (
    <aside className="fixed inset-y-0 start-0 z-30 hidden w-64 flex-col border-e border-line bg-sand px-4 py-6 lg:flex">
      <div className="flex items-center justify-between gap-2">
        <Link href="/" className="px-2" aria-label="Konsiliér AI"><Brand size={28} /></Link>
        <NotificationBell />
      </div>
      <Link href="/start" className="btn-primary mt-8 min-h-12 justify-between px-4 text-base">
        {t("app.newQuestion")}<Icon name="plus" size={20} />
      </Link>
      <nav aria-label={t("nav.main")} className="mt-6">
        <ul className="space-y-1">
          {tabs.map((tab) => {
            const on = tab.match(path);
            return (
              <li key={tab.key}>
                <Link href={tab.href} aria-current={on ? "page" : undefined}
                  className={`flex min-h-11 items-center gap-3 rounded-xl px-3 text-[15px] ${on ? "bg-sand-deep font-medium text-ink" : "text-ink-soft hover:bg-sand-deep"}`}>
                  <Icon name={tab.icon} size={20} className={on ? "text-ink" : "text-muted"} />{t(`app.tabs.${tab.key}`)}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
      {recent.length > 0 && (
        <div className="mt-8 min-h-0 overflow-y-auto">
          <p className="eyebrow px-3">{t("app.recent")}</p>
          <ul className="mt-2 space-y-0.5">
            {recent.map((c) => (
              <li key={c.id}>
                <Link href={`/case/${c.id}`} className="block truncate rounded-lg px-3 py-2 text-sm text-muted hover:bg-sand-deep hover:text-ink">{c.title}</Link>
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="mt-auto space-y-3 border-t border-line pt-4">
        {signed === false && (
          <SignInLink className="btn-ghost min-h-11 w-full justify-center gap-2 text-sm" />
        )}
        <LangSelect />
        <Link href="/" className="flex min-h-10 items-center justify-between rounded-xl px-3 text-sm text-ink-soft hover:bg-sand-deep">
          {t("app.toSite")}<Icon name="external" size={18} className="text-muted" />
        </Link>
      </div>
    </aside>
  );
}

/** Phone top bar of the app list screens: brand, «Войти» while not signed in, notifications and language. */
export function AppTopBar() {
  const signed = useSignedIn();
  return (
    <header className="sticky top-0 z-20 border-b border-ink/[0.08] bg-bar/92 pt-[env(safe-area-inset-top)] supports-[backdrop-filter]:bg-bar/80 supports-[backdrop-filter]:backdrop-blur-[20px] supports-[backdrop-filter]:backdrop-saturate-[1.8] lg:hidden">
      <div className="flex h-14 items-center justify-between px-5">
        <Link href="/" aria-label="Konsiliér AI"><Brand size={24} /></Link>
        <div className="flex items-center gap-1">
          {signed === false && (
            <SignInLink className="flex min-h-11 items-center gap-1.5 rounded-full px-3 text-sm font-medium text-brand hover:bg-ink/[0.05]" />
          )}
          <NotificationBell />
          <LangSelect />
        </div>
      </div>
    </header>
  );
}
