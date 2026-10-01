"use client";

import { useEffect, useState } from "react";
import { Icon } from "@/components/ui";
import { api } from "@/lib/api";
import { useT } from "@/lib/i18n";

type Ref = { code: string; link: string; invited: number; active: number };

/** The person's invite link: share (phone share sheet) or copy, and how many people came by it. The offer: when the
 *  invited friend pays for a document, both get one document free. */
export function Invite({ compact = false, big = false }: { compact?: boolean; big?: boolean }) {
  const t = useT();
  const [ref, setRef] = useState<Ref | null>(null);
  const [copied, setCopied] = useState(false);
  useEffect(() => { api<Ref>("/v1/referral").then(setRef).catch(() => {}); }, []);
  if (!ref) return null;

  async function share() {
    const text = t("invite.shareText");
    if (navigator.share) {
      try { await navigator.share({ title: "Konsiliér AI", text, url: ref!.link }); return; } catch { /* closed: fall back to copy */ }
    }
    try { await navigator.clipboard.writeText(`${text} ${ref!.link}`); setCopied(true); setTimeout(() => setCopied(false), 2500); } catch {}
  }

  const button = (
    <button type="button" onClick={share} className={compact ? "btn-ghost min-h-10" : "btn-primary min-h-12"}>
      <Icon name={copied ? "check" : "share"} size={18} />{copied ? t("invite.copied") : t("invite.share")}
    </button>
  );
  // owner 01.10 (referral, option A): after payment and on the ready document — a large block with ready messages
  if (big) {
    const via = (src: string) => `${ref.link}${ref.link.includes("?") ? "&" : "?"}src=${src}`;
    return (
      <section className="space-y-3 rounded-2xl bg-brand-50 p-5" aria-labelledby="invite-big-title">
        <h2 id="invite-big-title" className="text-xl font-semibold leading-snug">{t("invite.bigTitle")}</h2>
        <p className="text-[15px] text-ink-soft">{t("invite.bigLead")}</p>
        <div className="grid gap-2 sm:grid-cols-3">
          <a className="btn-primary min-h-12 justify-center" target="_blank" rel="noreferrer"
            href={`https://wa.me/?text=${encodeURIComponent(`${t("invite.shareText")} ${via("whatsapp")}`)}`}>WhatsApp</a>
          <a className="btn-primary min-h-12 justify-center" target="_blank" rel="noreferrer"
            href={`https://t.me/share/url?url=${encodeURIComponent(via("telegram"))}&text=${encodeURIComponent(t("invite.shareText"))}`}>Telegram</a>
          <button type="button" onClick={share} className="btn-ghost min-h-12 justify-center">
            <Icon name={copied ? "check" : "share"} size={18} />{copied ? t("invite.copied") : t("invite.other")}
          </button>
        </div>
        <p className="text-sm text-muted">{t("invite.invited", { n: ref.invited })}</p>
      </section>
    );
  }
  if (compact) {
    return (
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-line bg-sand px-4 py-3">
        <p className="min-w-0 flex-1 text-sm text-ink-soft">{t("invite.offer")}</p>
        {button}
      </div>
    );
  }
  return (
    <section className="space-y-3 rounded-2xl border border-line p-5" aria-labelledby="invite-title">
      <h2 id="invite-title" className="text-lg font-semibold">{t("invite.title")}</h2>
      <p className="flex items-start gap-2 text-sm font-medium text-ink"><Icon name="checkCircle" size={18} className="mt-0.5 shrink-0 text-brand" />{t("invite.offer")}</p>
      <p className="text-sm text-muted">{t("invite.lead")}</p>
      <p dir="ltr" className="truncate rounded-xl bg-sand px-3 py-2.5 font-mono text-sm text-ink">{ref.link}</p>
      <div className="flex flex-wrap items-center gap-3">
        {button}
        <span className="text-sm text-muted">{t("invite.invited", { n: ref.invited })}</span>
      </div>
    </section>
  );
}
