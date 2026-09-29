"use client";

import Link from "next/link";
import { Brand } from "@/components/Brand";
import { InstallApp } from "@/components/InstallApp";
import { Icon } from "@/components/ui";
import { SocialIcon } from "@/components/SocialIcon";
import { CONTACTS, SOCIALS } from "@/lib/contacts";
import { LAWYERS_PUBLIC } from "@/lib/features";
import { useT } from "@/lib/i18n";

export default function Footer() {
  const t = useT();
  return (
    <footer className="bg-sand">
      <div className="mx-auto grid max-w-[1208px] gap-6 px-5 py-10 text-sm sm:grid-cols-2 lg:grid-cols-4">
        <div className="space-y-2">
          <Brand size={26} />
          <p className="text-muted">{t("footer.said")}</p>
          <InstallApp className="pt-2" />
        </div>
        <nav aria-label={t("footer.product")} className="flex flex-col gap-2">
          <Link href="/how-it-works" className="inline-flex items-center text-muted hover:text-ink pointer-coarse:min-h-10">{t("nav.howItWorks")}</Link>
          <Link href="/coverage" className="inline-flex items-center text-muted hover:text-ink pointer-coarse:min-h-10">{t("nav.coverage")}</Link>
          <Link href="/app" className="inline-flex items-center text-muted hover:text-ink pointer-coarse:min-h-10">{t("nav.app")}</Link>
          <Link href="/support" className="inline-flex items-center text-muted hover:text-ink pointer-coarse:min-h-10">{t("footer.support")}</Link>
        </nav>
        {LAWYERS_PUBLIC && <nav aria-label={t("footer.lawyers")} className="flex flex-col gap-2">
          <Link href="/lawyers" className="inline-flex items-center text-muted hover:text-ink pointer-coarse:min-h-10">{t("nav.lawyers")}</Link>
          <Link href="/for-lawyers" className="inline-flex items-center text-muted hover:text-ink pointer-coarse:min-h-10">{t("nav.forLawyers")}</Link>
          <Link href="/lawyer" className="inline-flex items-center text-muted hover:text-ink pointer-coarse:min-h-10">{t("footer.lawyerCabinet")}</Link>
        </nav>}
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
      <div className="mx-auto max-w-[1208px] space-y-2 px-5 pb-8 text-xs text-muted">
        <p className="max-w-3xl">{t("legal.disclaimer")}</p>
        <p className="flex flex-wrap gap-x-3 gap-y-1">
          <Link href="/terms" className="link">{t("legal.terms")}</Link>
          <span dir="ltr">© Konsiliér AI · konsilier.com</span>
        </p>
      </div>
    </footer>
  );
}
