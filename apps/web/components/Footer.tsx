"use client";

import Link from "next/link";
import { InstallApp } from "@/components/InstallApp";
import { useT } from "@/lib/i18n";

export default function Footer() {
  const t = useT();
  return (
    <footer className="border-t border-line bg-sand">
      <div className="mx-auto grid max-w-6xl gap-6 px-4 py-10 text-sm sm:grid-cols-3">
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
      </div>
      <p className="mx-auto max-w-6xl px-4 pb-8 text-xs text-muted" dir="ltr">© Konsilier.AI · konsilier.com</p>
    </footer>
  );
}
