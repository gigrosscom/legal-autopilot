"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { PushToggle } from "@/components/PushToggle";
import { Icon } from "@/components/ui";
import { markRead, useInbox, type InboxItem } from "@/lib/inbox";
import { useLang, useT } from "@/lib/i18n";

const LOCALES: Record<string, string> = { ru: "ru-RU", kk: "kk-KZ", en: "en-GB", ar: "ar", tr: "tr-TR" };

/** The bell: unread count, and a list of notifications (newest first) with a link to the case each is about. */
export function NotificationBell({ className = "" }: { className?: string }) {
  const t = useT();
  const inbox = useInbox();
  const [open, setOpen] = useState(false);
  const close = useCallback(() => setOpen(false), []);  // stable: the panel keeps focus across polls
  const unread = inbox?.unread ?? 0;
  const label = unread > 0 ? t("inbox.titleUnread", { n: unread }) : t("inbox.title");
  return (
    <>
      <button type="button" onClick={() => setOpen(true)} aria-haspopup="dialog" aria-label={label} title={label}
        className={`relative flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-ink hover:bg-sand-deep ${className}`}>
        <Icon name="bell" size={22} />
        {unread > 0 && (
          <span aria-hidden="true"
            className="absolute -end-0.5 -top-0.5 flex h-5 min-w-5 items-center justify-center rounded-full bg-danger-strong px-1 text-[11px] font-semibold leading-none text-white tabular-nums">
            {unread > 99 ? "99+" : unread}
          </span>
        )}
      </button>
      {/* on the body: the sidebar and the case screen are stacking contexts of their own */}
      {open && createPortal(<InboxPanel items={inbox?.items ?? []} unread={unread} loading={inbox === null}
        onClose={close} />, document.body)}
    </>
  );
}

function InboxPanel({ items, unread, loading, onClose }: {
  items: InboxItem[]; unread: number; loading: boolean; onClose: () => void;
}) {
  const t = useT();
  const { lang } = useLang();
  const panel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", esc);
    panel.current?.focus();
    return () => document.removeEventListener("keydown", esc);
  }, [onClose]);
  const when = (iso: string) => new Date(iso).toLocaleString(LOCALES[lang] ?? "ru-RU",
    { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center" role="dialog" aria-modal="true"
      aria-label={t("inbox.title")}>
      <button type="button" aria-label={t("app.close")} onClick={onClose} className="absolute inset-0 bg-ink/40" />
      <div ref={panel} tabIndex={-1}
        className="relative flex max-h-[88dvh] w-full max-w-lg flex-col rounded-t-3xl bg-surface pb-[env(safe-area-inset-bottom)] shadow-[var(--shadow-raised)] outline-none sm:rounded-3xl">
        <div className="flex items-center gap-2 border-b border-line py-2 ps-5 pe-2">
          <h2 className="flex-1 truncate font-semibold">{t("inbox.title")}</h2>
          {unread > 0 && (
            <button type="button" onClick={() => markRead({ all: true })}
              className="min-h-10 rounded-xl px-3 text-sm font-medium text-brand hover:bg-sand">{t("inbox.readAll")}</button>
          )}
          <button type="button" onClick={onClose} aria-label={t("app.close")}
            className="flex h-11 w-11 items-center justify-center rounded-full hover:bg-sand"><Icon name="x" size={22} /></button>
        </div>
        <div className="overflow-y-auto overscroll-contain">
          <PushToggle compact className="border-b border-line" />
          {loading && <p className="p-5 text-sm text-muted">{t("common.loading")}</p>}
          {!loading && items.length === 0 && (
            <div className="flex flex-col items-center gap-2 p-8 text-center">
              <Icon name="bell" size={28} className="text-muted" />
              <p className="text-sm text-muted">{t("inbox.empty")}</p>
            </div>
          )}
          <ul className="divide-y divide-line">
            {items.map((n) => {
              const href = n.case_id ? `/case/${n.case_id}` : n.kind === "desk_message" ? "/support" : null;
              const fresh = !n.read_at;
              return (
                <li key={n.id} className={`flex gap-3 px-5 py-4 ${fresh ? "bg-brand-50" : ""}`}>
                  <span aria-hidden="true" className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${fresh ? "bg-brand" : "bg-transparent"}`} />
                  <div className="min-w-0 flex-1 space-y-1.5">
                    <p className={`whitespace-pre-line text-sm leading-snug ${fresh ? "font-medium text-ink" : "text-ink-soft"}`}>
                      {fresh && <span className="sr-only">{t("inbox.new")}: </span>}{n.text}
                    </p>
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
                      <time dateTime={n.created_at} className="tabular-nums">{when(n.created_at)}</time>
                      {href && (
                        <Link href={href} onClick={() => { if (fresh) markRead({ ids: [n.id] }); onClose(); }}
                          className="inline-flex min-h-8 items-center gap-1 font-medium text-brand hover:underline">
                          {t(n.case_id ? "inbox.openCase" : "inbox.openSupport")}
                          <Icon name="arrowRight" size={14} className="rtl:-scale-x-100" />
                        </Link>
                      )}
                      {fresh && (
                        <button type="button" onClick={() => markRead({ ids: [n.id] })}
                          className="min-h-8 font-medium hover:text-ink">{t("inbox.markRead")}</button>
                      )}
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      </div>
    </div>
  );
}
