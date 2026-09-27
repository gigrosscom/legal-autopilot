"use client";

import Link from "next/link";
import { useT } from "@/lib/i18n";

const ITEMS = [
  { icon: "🛡️", key: "verified" },
  { icon: "🔒", key: "escrow", soon: true },
  { icon: "📊", key: "rating" },
  { icon: "🗺️", key: "roadmap" },
];

export default function Trust() {
  const t = useT();
  return (
    <section className="space-y-4">
      <h2 className="text-2xl font-bold">{t("trust.title")}</h2>
      <div className="grid gap-4 md:grid-cols-2">
        {ITEMS.map((it) => (
          <div key={it.key} className="card space-y-2">
            <div className="flex items-center gap-2">
              <span className="text-xl">{it.icon}</span>
              <h3 className="font-semibold">{t(`trust.${it.key}Title`)}</h3>
              {it.soon && <span className="chip bg-amber-100 text-amber-900">{t("trust.soon")}</span>}
            </div>
            <p className="text-sm text-ink/70">{t(`trust.${it.key}`)}</p>
          </div>
        ))}
      </div>
      <Link href="/lawyers" className="btn-ghost">{t("trust.cta")} →</Link>
    </section>
  );
}
