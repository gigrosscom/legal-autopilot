"use client";

import Link from "next/link";
import { useT } from "@/lib/i18n";

/** 404 in the site's own design (Next.js's default page is always white, also in the dark theme). */
export default function NotFound() {
  const t = useT();
  return (
    <div className="mx-auto flex max-w-md flex-col items-center gap-4 py-20 text-center">
      <p className="text-[56px] leading-none font-semibold text-faint">404</p>
      <h1 className="text-2xl font-semibold">{t("notFoundPage.title")}</h1>
      <Link href="/" className="btn-primary">{t("notFoundPage.home")}</Link>
    </div>
  );
}
