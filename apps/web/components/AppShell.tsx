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
export function AppShell({ title, subtitle, back = "/cases", sections = [], links = [], children, bar, scrollKey,
  wallpaper = false, avatar = false, tabs = true }: {
  title: string; subtitle?: string; back?: string; sections?: MoreSection[]; links?: MoreLink[];
  children: ReactNode; bar?: ReactNode; scrollKey?: unknown;
  wallpaper?: boolean;  // the chat's messenger background
  avatar?: boolean;     // Konsiliér's icon beside the title, as a contact in a messenger
  tabs?: boolean;       // the app's tab bar under the screen (a conversation hides it, as the messengers do)
}) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const [keyboard, setKeyboard] = useState(false);
  const end = useRef<HTMLDivElement>(null);
  const root = useRef<HTMLDivElement>(null);
  const scroller = useRef<HTMLElement>(null);
  const [below, setBelow] = useState(false);  // scrolled up: the «down» button shows
  // a field in the conversation (the draft's blanks, a form in a card) is being typed in: the keyboard must not
  // carry the page to its end, and the bottom bar must not cover the field (owner 01.10, iPhone)
  const [field, setField] = useState(false);

  // Scroll only the conversation itself. `scrollIntoView` also scrolls every ancestor, the page included: on iPhone the
  // page under this fixed screen then moved, Safari's toolbars collapsed and 100dvh changed, so the whole screen with
  // its bottom bar and tab bar «floated» at every new message (owner 02.10).
  const toEnd = (smooth = false) => {
    const box = scroller.current;
    if (box) box.scrollTo({ top: box.scrollHeight, behavior: smooth ? "smooth" : "auto" });
  };
  const centre = (el: HTMLElement) => {
    const box = scroller.current;
    if (!box) return;
    const r = el.getBoundingClientRect(), b = box.getBoundingClientRect();
    box.scrollTo({ top: box.scrollTop + r.top - b.top - Math.max(0, (b.height - r.height) / 2) });
  };

  useEffect(() => { pinned.current = true; toEnd(); }, [scrollKey]);

  // Cards load their parts after the jump to the end (the document card, «Отправьте другу»…): while the person is at
  // the end, the conversation stays at the end as it grows, as in a messenger, instead of the end sliding away.
  const pinned = useRef(true);
  const content = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = content.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(() => { if (pinned.current && !contentField(scroller.current)) toEnd(); });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // The page under this full-screen layout must not scroll at all (the conversation is the only thing that scrolls):
  // otherwise a swipe past the end of the conversation carried the page, and the bars with it, on iPhone.
  useEffect(() => {
    const html = document.documentElement, body = document.body;
    const was = [html.style.overflow, body.style.overflow, html.style.overscrollBehavior, body.style.overscrollBehavior];
    html.style.overflow = body.style.overflow = "hidden";
    html.style.overscrollBehavior = body.style.overscrollBehavior = "none";
    window.scrollTo(0, 0);
    return () => { [html.style.overflow, body.style.overflow, html.style.overscrollBehavior, body.style.overscrollBehavior] = was; };
  }, []);

  // iOS Safari does not resize the layout for the keyboard: follow the visual viewport so the input bar
  // stays right above the keyboard and the top bar stays in view.
  useEffect(() => {
    const vv = window.visualViewport;
    const el = root.current;
    if (!vv || !el) return;
    const fit = () => {
      const open = window.innerHeight - vv.height > 150;  // the keyboard is up
      // only while the keyboard is up: iOS (above all a Home-screen app) does not always report the viewport's
      // full height again after the keyboard closes, and a height left from it cut every screen short (owner 02.10)
      el.style.height = open ? `${vv.height}px` : "";
      el.style.transform = open && vv.offsetTop ? `translateY(${vv.offsetTop}px)` : "";
      setKeyboard(open);  // the tab bar gives its room to the keyboard
      const typing = contentField(scroller.current);
      if (typing) centre(typing);  // the field stays in sight above the keyboard
      else toEnd();
    };
    // the keyboard closing is not always followed by a resize event: look again once the field has let go
    const later = () => { [100, 400].forEach((ms) => setTimeout(fit, ms)); };
    fit();
    vv.addEventListener("resize", fit);
    vv.addEventListener("scroll", fit);
    window.addEventListener("focusout", later);
    window.addEventListener("orientationchange", later);
    window.addEventListener("pageshow", fit);
    return () => {
      vv.removeEventListener("resize", fit); vv.removeEventListener("scroll", fit);
      window.removeEventListener("focusout", later); window.removeEventListener("orientationchange", later);
      window.removeEventListener("pageshow", fit);
    };
  }, []);

  const showBar = !!bar && !(keyboard && field);

  return (
    <div ref={root} className="fixed inset-x-0 top-0 z-40 flex h-[var(--app-h,100dvh)] flex-col bg-surface lg:start-64">
      <header className="border-b border-line bg-surface pt-[env(safe-area-inset-top)]">
        <div className="mx-auto flex min-h-14 max-w-3xl items-center gap-1 px-2 py-1 lg:h-16 lg:px-6">
          <Link href={back} aria-label={t("app.back")}
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-ink hover:bg-sand">
            <Icon name="arrowRight" size={22} className="rotate-180 rtl:rotate-0" />
          </Link>
          {avatar && <img src="/icons/icon-192.png" alt="" width={36} height={36} className="me-2 h-9 w-9 shrink-0 rounded-full ring-1 ring-line" />}
          <div className="min-w-0 flex-1">
            <h1 className="truncate text-[17px] font-bold leading-tight text-ink">{title}</h1>
            {subtitle && <p className="line-clamp-2 text-xs leading-tight text-muted text-balance">{subtitle}</p>}
          </div>
          <NotificationBell className="lg:hidden" />
          <button type="button" onClick={() => setOpen(true)} aria-haspopup="dialog" title={t("app.more")}
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-ink hover:bg-sand">
            <Icon name="menu" size={21} /><span className="sr-only">{t("app.more")}</span>
          </button>
        </div>
      </header>

      <div className="relative flex min-h-0 flex-1 flex-col">
      <main id="main" ref={scroller}
        onFocus={(e) => {
          const el = contentField(e.currentTarget);
          setField(!!el);
          // after the keyboard has opened (iOS animates it ~300 ms): the field in the middle of what is left
          if (el) [60, 350].forEach((ms) => setTimeout(() => { if (document.activeElement === el) centre(el); }, ms));
        }}
        onBlur={(e) => { const box = e.currentTarget; setTimeout(() => setField(!!contentField(box)), 0); }}
        onScroll={(e) => {
        const el = e.currentTarget;
        const left = el.scrollHeight - el.scrollTop - el.clientHeight;
        setBelow(left > 240);
        pinned.current = left < 48;
      }}
        className={`min-h-0 flex-1 overflow-y-auto overscroll-contain ${wallpaper ? "chat-wallpaper" : ""}`}>
        {/* pb-8: the last card ends clear above the bottom bar (and the «down» button on its edge) */}
        <div ref={content} className="mx-auto max-w-3xl space-y-3 px-5 pt-5 pb-8 lg:px-8">
          {children}
          <div ref={end} />
        </div>
      </main>
        {/* «down» floats in the conversation's own corner, above the bottom bar (as in WhatsApp), not in the text flow (owner 02.10) */}
        {below && (
          <button type="button" onClick={() => toEnd(true)} aria-label={t("app.toEnd")}
            className="absolute bottom-3 end-3 z-10 flex h-10 w-10 items-center justify-center rounded-full bg-surface text-ink ring-1 ring-line shadow-[0_2px_8px_rgb(0_0_0/0.12)]">
            <Icon name="chevronDown" size={20} />
          </button>
        )}
      </div>

      {showBar && (
        <div className={`border-t border-line ${wallpaper ? "bg-[var(--chat-bg)]" : "bg-surface"} ${keyboard ? "pb-2" : tabs ? "pb-2 lg:pb-[max(env(safe-area-inset-bottom),0.75rem)]" : "pb-[max(env(safe-area-inset-bottom),0.5rem)] lg:pb-[max(env(safe-area-inset-bottom),0.75rem)]"}`}>
          <div className="mx-auto max-w-3xl px-3 pt-2 lg:px-8">{bar}</div>
        </div>
      )}
      {!keyboard && tabs && <TabBar inline />}

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

/** The focused text field inside the conversation, if any (not the input bar below it). */
function contentField(box: HTMLElement | null): HTMLElement | null {
  const el = document.activeElement;
  if (!box || !(el instanceof HTMLElement) || !box.contains(el)) return null;
  return el.matches("input:not([type=checkbox]):not([type=radio]):not([type=file]), textarea, select, [contenteditable=true]") ? el : null;
}
