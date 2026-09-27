"use client";

import Link from "next/link";
import { useLang, useT } from "@/lib/i18n";

export default function Header() {
  const t = useT();
  const { lang, setLang } = useLang();
  return (
    <header className="border-b border-ink/10 bg-white/70 backdrop-blur">
      <div className="mx-auto flex max-w-5xl items-center justify-between gap-4 px-4 py-3">
        <Link href="/" className="text-lg font-bold tracking-tight">
          Konsilier<span className="text-brand">.AI</span>
        </Link>
        <nav className="flex items-center gap-4 text-sm">
          <Link href="/start" className="hover:text-brand">{t("nav.start")}</Link>
          <Link href="/lawyers" className="hover:text-brand">{t("nav.lawyers")}</Link>
          <Link href="/cases" className="hover:text-brand">{t("nav.cases")}</Link>
          <div className="flex overflow-hidden rounded-lg border border-ink/15 text-xs">
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
        </nav>
      </div>
    </header>
  );
}
