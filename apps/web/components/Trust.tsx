"use client";

import Link from "next/link";
import { useState } from "react";
import { useT } from "@/lib/i18n";

const ITEMS = [
  { icon: "🛡️", key: "verified", href: "/for-lawyers" },
  { icon: "🔒", key: "escrow", soon: true },
  { icon: "📊", key: "rating", href: "/lawyers" },
  { icon: "🗺️", key: "roadmap", href: "/start" },
];

export default function Trust() {
  const t = useT();
  const [open, setOpen] = useState<string | null>(null);
  return (
    <section className="space-y-4">
      <h2 className="text-2xl font-bold">{t("trust.title")}</h2>
      <div className="grid gap-4 md:grid-cols-2 md:items-start">
        {ITEMS.map((it) => {
          const isOpen = open === it.key;
          return (
            <div key={it.key} className={`card space-y-2 transition ${isOpen ? "ring-2 ring-brand/40" : "hover:shadow-md"}`}>
              <button
                type="button"
                aria-expanded={isOpen}
                onClick={() => setOpen(isOpen ? null : it.key)}
                className="w-full space-y-2 text-left"
              >
                <div className="flex items-start gap-2">
                  <span className="text-xl">{it.icon}</span>
                  <h3 className="flex-1 font-semibold">{t(`trust.${it.key}Title`)}</h3>
                  <span className={`mt-0.5 text-brand transition-transform ${isOpen ? "rotate-180" : ""}`} aria-hidden>▾</span>
                </div>
                {it.soon && <span className="chip bg-amber-100 text-amber-900">{t("trust.soon")}</span>}
                <p className="text-sm text-ink/70">{t(`trust.${it.key}`)}</p>
                {!isOpen && <span className="text-sm font-medium text-brand">{t("trust.more")} →</span>}
              </button>
              {isOpen && (
                <div className="space-y-3 border-t border-ink/10 pt-3 text-sm">
                  <ul className="space-y-2">
                    {t(`trust.${it.key}More`).split("\n").map((line) => (
                      <li key={line} className="flex gap-2">
                        <span className="text-brand">✓</span>
                        <span>{line}</span>
                      </li>
                    ))}
                  </ul>
                  <p className="rounded-lg bg-ink/5 p-3 text-ink/80">
                    <span className="font-semibold">{t("trust.now")}: </span>
                    {t(`trust.${it.key}Now`)}
                  </p>
                  <div className="flex flex-wrap items-center gap-3">
                    {it.href && <Link href={it.href} className="btn-primary">{t(`trust.${it.key}Link`)} →</Link>}
                    <button type="button" onClick={() => setOpen(null)} className="text-ink/60 hover:text-ink">{t("trust.less")}</button>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
      <div className="flex flex-wrap gap-2">
        <Link href="/lawyers" className="btn-ghost">{t("trust.cta")} →</Link>
        <Link href="/for-lawyers" className="btn-primary">{t("trust.joinLawyer")} →</Link>
      </div>
    </section>
  );
}
