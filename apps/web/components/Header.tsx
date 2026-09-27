"use client";

import Link from "next/link";
import { useLang, useT } from "@/lib/i18n";

export default function Header() {
  const t = useT();
  const { lang, setLang } = useLang();
  return (
    <header className="border-b border-ink/10 bg-white/70 backdrop-blur">
      {/* Phones: logo + language on the first row, sections on a second row (scrolls if needed). */}
      <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-x-4 gap-y-2 px-4 py-3">
        <Link href="/" className="text-lg font-bold tracking-tight">
          Konsilier<span className="text-brand">.AI</span>
        </Link>
        <nav className="order-last flex w-full items-center justify-between gap-3 overflow-x-auto whitespace-nowrap text-sm sm:order-none sm:w-auto sm:justify-start sm:gap-4">
          <Link href="/start" className="hover:text-brand">{t("nav.start")}</Link>
          <Link href="/lawyers" className="hover:text-brand">{t("nav.lawyers")}</Link>
          <Link href="/for-lawyers" className="font-semibold text-brand hover:underline">{t("nav.forLawyers")}</Link>
          <Link href="/cases" className="hover:text-brand">{t("nav.cases")}</Link>
        </nav>
        <div className="flex shrink-0 overflow-hidden rounded-lg border border-ink/15 text-xs">
          {(["ru", "kk"] as const).map((l) => (
            <button
              key={l}
              onClick={() => setLang(l)}
              className={`px-2 py-1 uppercase ${lang === l ? "bg-ink text-white" : "bg-white"}`}
            >
              {l}
            </button>
          ))}
        </div>
      </div>
    </header>
  );
}
