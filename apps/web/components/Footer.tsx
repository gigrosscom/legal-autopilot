"use client";

import Link from "next/link";
import { InstallApp } from "@/components/InstallApp";
import { Icon } from "@/components/ui";
import { SocialIcon } from "@/components/SocialIcon";
import { CONTACTS, SOCIALS } from "@/lib/contacts";
import { useT } from "@/lib/i18n";

export default function Footer() {
  const t = useT();
  return (
    <footer className="border-t border-line bg-sand">
      <div className="mx-auto grid max-w-6xl gap-6 px-4 py-10 text-sm sm:grid-cols-2 lg:grid-cols-4">
        <div className="space-y-2">
          <p className="text-base font-bold" dir="ltr">Konsilier<span className="text-brand">.AI</span></p>
          <p className="text-muted">{t("footer.tagline")}</p>
          <InstallApp className="pt-2" />
        </div>
        <nav aria-label={t("footer.product")} className="flex flex-col gap-2">
          <Link href="/how-it-works" className="inline-flex items-center text-muted hover:text-ink pointer-coarse:min-h-10">{t("nav.howItWorks")}</Link>
          <Link href="/coverage" className="inline-flex items-center text-muted hover:text-ink pointer-coarse:min-h-10">{t("nav.coverage")}</Link>
        </nav>
        <nav aria-label={t("footer.lawyers")} className="flex flex-col gap-2">
          <Link href="/lawyers" className="inline-flex items-center text-muted hover:text-ink pointer-coarse:min-h-10">{t("nav.lawyers")}</Link>
          <Link href="/for-lawyers" className="inline-flex items-center text-muted hover:text-ink pointer-coarse:min-h-10">{t("nav.forLawyers")}</Link>
          <Link href="/lawyer" className="inline-flex items-center text-muted hover:text-ink pointer-coarse:min-h-10">{t("footer.lawyerCabinet")}</Link>
        </nav>
        <div className="space-y-3">
          <p className="font-semibold">{t("footer.contacts")}</p>
          {CONTACTS.address && (
            <p className="flex items-start gap-2 text-muted"><Icon name="building" size={18} className="mt-0.5" />{CONTACTS.address}</p>
          )}
          {CONTACTS.email && (
            <a href={`mailto:${CONTACTS.email}`} className="flex items-center gap-2 text-muted hover:text-ink pointer-coarse:min-h-10">
              <Icon name="mail" size={18} />{CONTACTS.email}
            </a>
          )}
          <p className="text-muted" dir="ltr">@konsilier.ai</p>
          <ul className="flex flex-wrap gap-2" aria-label={t("footer.contacts")}>
            {SOCIALS.map((s) => (
              <li key={s.key}>
                <a href={s.url} target="_blank" rel="noopener noreferrer" aria-label={s.label} title={s.label}
                  className="flex h-11 w-11 items-center justify-center rounded-xl border border-line bg-surface text-muted hover:border-brand hover:text-brand">
                  <SocialIcon name={s.key} />
                </a>
              </li>
            ))}
          </ul>
        </div>
      </div>
      <p className="mx-auto max-w-6xl px-4 pb-8 text-xs text-muted" dir="ltr">© Konsilier.AI · konsilier.com</p>
    </footer>
  );
}
