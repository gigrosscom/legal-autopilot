"use client";

import Link from "next/link";
import { useT } from "@/lib/i18n";

export default function Footer() {
  const t = useT();
  return (
    <footer className="border-t border-line bg-sand">
      <div className="mx-auto grid max-w-6xl gap-6 px-4 py-10 text-sm sm:grid-cols-3">
        <div className="space-y-2">
          <p className="text-base font-bold" dir="ltr">Konsilier<span className="text-brand">.AI</span></p>
          <p className="text-muted">{t("footer.tagline")}</p>
        </div>
        <nav aria-label={t("footer.product")} className="flex flex-col gap-2">
          <Link href="/how-it-works" className="text-muted hover:text-ink">{t("nav.howItWorks")}</Link>
          <Link href="/coverage" className="text-muted hover:text-ink">{t("nav.coverage")}</Link>
        </nav>
        <nav aria-label={t("footer.lawyers")} className="flex flex-col gap-2">
          <Link href="/lawyers" className="text-muted hover:text-ink">{t("nav.lawyers")}</Link>
          <Link href="/for-lawyers" className="text-muted hover:text-ink">{t("nav.forLawyers")}</Link>
          <Link href="/lawyer" className="text-muted hover:text-ink">{t("footer.lawyerCabinet")}</Link>
        </nav>
      </div>
      <p className="mx-auto max-w-6xl px-4 pb-8 text-xs text-muted" dir="ltr">© Konsilier.AI · konsilier.com</p>
    </footer>
  );
}
