"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { TabBar } from "@/components/AppNav";
import { NotificationBell } from "@/components/NotificationBell";
import { Icon, type IconName } from "@/components/ui";
import { useT } from "@/lib/i18n";

export type MoreSection = { key: string; icon: IconName; label: string; render: () => ReactNode };
export type MoreLink = { href: string; icon: IconName; label: string };

/**
 * Full-screen app layout for a case: a fixed top bar (back · title · bell · «Ещё»; on desktop the bell is in the
 * sidebar), the conversation in the middle (the only part that scrolls) and a fixed input bar at the bottom. Everything secondary lives in the «Ещё»
 * sheet, so the screen never grows panels under the conversation.
 */
export function AppShell({ title, subtitle, back = "/cases", sections = [], links = [], children, bar, scrollKey }: {
  title: string; subtitle?: string; back?: string; sections?: MoreSection[]; links?: MoreLink[];
  children: ReactNode; bar?: ReactNode; scrollKey?: unknown;
}) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const [keyboard, setKeyboard] = useState(false);
  const end = useRef<HTMLDivElement>(null);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => { end.current?.scrollIntoView({ block: "end" }); }, [scrollKey]);

  // iOS Safari does not resize the layout for the keyboard: follow the visual viewport so the input bar
  // stays right above the keyboard and the top bar stays in view.
  useEffect(() => {
    const vv = window.visualViewport;
    const el = root.current;
    if (!vv || !el) return;
    const fit = () => {
      el.style.height = `${vv.height}px`;
      el.style.transform = `translateY(${vv.offsetTop}px)`;
      setKeyboard(window.innerHeight - vv.height > 150);  // the tab bar gives its room to the keyboard
      end.current?.scrollIntoView({ block: "end" });
    };
    fit();
    vv.addEventListener("resize", fit);
    vv.addEventListener("scroll", fit);
    return () => { vv.removeEventListener("resize", fit); vv.removeEventListener("scroll", fit); };
  }, []);

  return (
    <div ref={root} className="fixed inset-x-0 top-0 z-40 flex h-dvh flex-col bg-surface lg:start-64">
      <header className="border-b border-line bg-surface pt-[env(safe-area-inset-top)]">
        <div className="mx-auto flex h-14 max-w-3xl items-center gap-1 px-2 lg:h-16 lg:px-6">
          <Link href={back} aria-label={t("app.back")}
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-ink hover:bg-sand">
            <Icon name="arrowRight" size={22} className="rotate-180 rtl:rotate-0" />
          </Link>
          <div className="min-w-0 flex-1">
            <h1 className="truncate text-base font-semibold leading-tight">{title}</h1>
            {subtitle && <p className="truncate text-xs text-muted">{subtitle}</p>}
          </div>
          <NotificationBell className="lg:hidden" />
          <button type="button" onClick={() => setOpen(true)} aria-haspopup="dialog"
            className="flex h-10 shrink-0 items-center gap-1.5 rounded-xl border border-line px-3.5 text-sm font-medium hover:bg-sand">
            <Icon name="menu" size={18} />{t("app.more")}
          </button>
        </div>
      </header>

      <main id="main" className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
        <div className="mx-auto max-w-3xl space-y-3 px-5 py-5 lg:px-8">
          {children}
          <div ref={end} />
        </div>
      </main>

      {bar && (
        <div className={`bg-surface ${keyboard ? "pb-2" : "pb-2 lg:pb-[max(env(safe-area-inset-bottom),0.75rem)]"}`}>
          <div className="mx-auto max-w-3xl px-3 pt-2 lg:px-8">{bar}</div>
        </div>
      )}
      {!keyboard && <TabBar inline />}

      {open && <MoreSheet sections={sections} links={links} onClose={() => setOpen(false)} />}
    </div>
  );
}

function MoreSheet({ sections, links, onClose }: { sections: MoreSection[]; links: MoreLink[]; onClose: () => void }) {
  const t = useT();
  const [active, setActive] = useState<MoreSection | null>(null);
  const panel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") (active ? setActive(null) : onClose()); };
    document.addEventListener("keydown", esc);
    panel.current?.focus();
    return () => document.removeEventListener("keydown", esc);
  }, [active, onClose]);

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center" role="dialog" aria-modal="true"
      aria-label={active?.label ?? t("app.more")}>
      <button type="button" aria-label={t("app.close")} onClick={onClose} className="absolute inset-0 bg-ink/40" />
      <div ref={panel} tabIndex={-1}
        className="relative flex max-h-[88dvh] w-full max-w-2xl flex-col rounded-t-3xl bg-surface pb-[env(safe-area-inset-bottom)] shadow-[var(--shadow-raised)] outline-none sm:rounded-3xl">
        <div className="flex items-center gap-1 border-b border-line px-2 py-2">
          {active ? (
            <button type="button" onClick={() => setActive(null)} aria-label={t("app.back")}
              className="flex h-11 w-11 items-center justify-center rounded-full hover:bg-sand">
              <Icon name="arrowRight" size={22} className="rotate-180 rtl:rotate-0" />
            </button>
          ) : <span className="w-3" />}
          <h2 className="flex-1 truncate font-semibold">{active?.label ?? t("app.more")}</h2>
          <button type="button" onClick={onClose} aria-label={t("app.close")}
            className="flex h-11 w-11 items-center justify-center rounded-full hover:bg-sand"><Icon name="x" size={22} /></button>
        </div>
        <div className="overflow-y-auto overscroll-contain p-4">
          {active ? <div className="space-y-4">{active.render()}</div> : (
            <nav className="space-y-4">
              {sections.length > 0 && (
                <ul className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                  {sections.map((s) => (
                    <li key={s.key}>
                      <button type="button" onClick={() => setActive(s)}
                        className="flex min-h-20 w-full flex-col items-start justify-between gap-2 rounded-2xl border border-line bg-sand p-3 text-start text-sm font-semibold hover:border-brand">
                        <Icon name={s.icon} size={22} className="text-brand" />{s.label}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
              {links.length > 0 && (
                <ul className="divide-y divide-line rounded-2xl border border-line">
                  {links.map((l) => (
                    <li key={l.href}>
                      <Link href={l.href} onClick={onClose}
                        className="flex min-h-12 items-center gap-3 px-4 text-sm font-medium hover:text-brand">
                        <Icon name={l.icon} size={20} className="text-brand" /><span className="flex-1">{l.label}</span>
                        <Icon name="arrowRight" size={16} className="text-muted rtl:-scale-x-100" />
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </nav>
          )}
        </div>
      </div>
    </div>
  );
}
