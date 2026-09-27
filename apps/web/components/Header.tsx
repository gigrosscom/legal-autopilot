"use client";

import Link from "next/link";
import { useLang, useT } from "@/lib/i18n";

export default function Header() {
  const t = useT();
  const { lang, setLang } = useLang();
  return (
    <header className="border-b border-ink/10 bg-white">
      {/* Phones: logo + language on the first row, sections below (wrap on the narrowest screens). */}
      <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-x-4 gap-y-2 px-4 py-2">
        <Link href="/" className="py-2 text-lg font-bold tracking-tight">
          Konsilier<span className="text-brand">.AI</span>
        </Link>
        <nav className="order-last flex w-full flex-wrap items-center gap-x-3 gap-y-0 whitespace-nowrap text-sm min-[360px]:justify-between sm:order-none sm:w-auto sm:justify-start sm:gap-4">
          <Link href="/start" className="py-2.5 hover:text-brand">{t("nav.start")}</Link>
          <Link href="/lawyers" className="py-2.5 hover:text-brand">{t("nav.lawyers")}</Link>
          <Link href="/for-lawyers" className="py-2.5 font-semibold text-brand hover:underline">{t("nav.forLawyers")}</Link>
          <Link href="/cases" className="py-2.5 hover:text-brand">{t("nav.cases")}</Link>
        </nav>
        <div className="flex shrink-0 overflow-hidden rounded-lg border border-ink/15 text-xs">
          {(["ru", "kk"] as const).map((l) => (
            <button
              key={l}
              onClick={() => setLang(l)}
              className={`min-h-9 px-3 py-1.5 uppercase ${lang === l ? "bg-ink text-white" : "bg-white"}`}
            >
              {l}
            </button>
          ))}
        </div>
      </div>
    </header>
  );
}
