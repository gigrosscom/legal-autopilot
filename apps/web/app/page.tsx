"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { publicApi, TELEGRAM_BOT, errorText } from "@/lib/api";
import { useLang, useT } from "@/lib/i18n";
import Trust from "@/components/Trust";

type Pack = {
  country: string;
  name: string;
  scenarios: { id: string; title: string; summary: string; price: { amount: number; currency: string } }[];
};

// Countries shown in the selector. Only the ones with a jurisdiction pack are "live";
// the rest collect a waitlist. (UI list only — legal data lives in packs/.)
const COUNTRIES: { code: string; ru: string; kk: string }[] = [
  { code: "KZ", ru: "Казахстан", kk: "Қазақстан" },
  { code: "UZ", ru: "Узбекистан", kk: "Өзбекстан" },
  { code: "KG", ru: "Кыргызстан", kk: "Қырғызстан" },
  { code: "AZ", ru: "Азербайджан", kk: "Әзірбайжан" },
  { code: "GE", ru: "Грузия", kk: "Грузия" },
  { code: "AM", ru: "Армения", kk: "Армения" },
  { code: "TR", ru: "Турция", kk: "Түркия" },
  { code: "AE", ru: "ОАЭ", kk: "БАӘ" },
  { code: "RS", ru: "Сербия", kk: "Сербия" },
  { code: "OTHER", ru: "Другая страна", kk: "Басқа ел" },
];

export default function Landing() {
  const t = useT();
  const { lang } = useLang();
  const [packs, setPacks] = useState<Pack[] | null>(null);
  const [country, setCountry] = useState("KZ");
  const [contact, setContact] = useState("");
  const [problem, setProblem] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    publicApi<Pack[]>(`/v1/packs?lang=${lang}`).then(setPacks).catch(() => setPacks([]));
  }, [lang]);

  const live = new Set((packs ?? []).map((p) => p.country));
  const pack = packs?.find((p) => p.country === country);

  async function joinWaitlist(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await publicApi("/v1/waitlist", {
        method: "POST",
        body: JSON.stringify({ country: country === "OTHER" ? "ZZ" : country, contact, problem: problem || null, language: lang }),
      });
      setSent(true);
    } catch (err) {
      setError(errorText(err));
    }
  }

  return (
    <div className="space-y-14">
      <section className="grid gap-8 pt-6 md:grid-cols-[1.4fr_1fr] md:items-center">
        <div className="space-y-5">
          <h1 className="text-3xl font-bold leading-tight tracking-tight md:text-4xl">{t("landing.promise")}</h1>
          <p className="text-base text-ink/70 sm:text-lg">{t("landing.sub")}</p>
          <div className="flex flex-wrap gap-3">
            <Link href="/start" className="btn-primary px-6 py-3 text-base">{t("landing.startWeb")}</Link>
            <a href={`https://t.me/${TELEGRAM_BOT}`} target="_blank" rel="noreferrer" className="btn-ghost px-6 py-3 text-base">
              {t("landing.startTelegram")}
            </a>
          </div>
          <p className="text-xs text-ink/50">{t("landing.disclaimer")}</p>
          <ul className="space-y-2 border-t border-ink/10 pt-4">
            {[["📄", "usp1"], ["⏰", "usp2"], ["👩‍⚖️", "usp3"]].map(([icon, k]) => (
              <li key={k} className="flex gap-3 font-medium">
                <span aria-hidden>{icon}</span>
                <span>{t(`landing.${k}`)}</span>
              </li>
            ))}
          </ul>
        </div>
        <div className="card space-y-3">
          <h2 className="font-semibold">{t("landing.howTitle")}</h2>
          <ol className="space-y-2 text-sm">
            {["how1", "how2", "how3", "how4"].map((k, i) => (
              <li key={k} className="flex gap-3">
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand text-xs font-bold text-white">{i + 1}</span>
                <span>{t(`landing.${k}`)}</span>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-2xl font-bold">{t("landing.scenariosTitle")}</h2>
          <label className="flex w-full flex-wrap items-center gap-2 text-sm sm:w-auto">
            {t("landing.countryTitle")}:
            <select className="input sm:w-auto" value={country} onChange={(e) => { setCountry(e.target.value); setSent(false); }}>
              {COUNTRIES.map((c) => (
                <option key={c.code} value={c.code}>
                  {c[lang]} — {live.has(c.code) ? t("landing.countryLive") : t("landing.countrySoon")}
                </option>
              ))}
            </select>
          </label>
        </div>

        {packs === null ? (
          <p className="text-ink/50">{t("common.loading")}</p>
        ) : pack ? (
          <div className="grid gap-4 md:grid-cols-2">
            {pack.scenarios.map((s) => (
              <div key={s.id} className="card flex flex-col gap-3">
                <h3 className="text-lg font-semibold">{s.title}</h3>
                <p className="flex-1 text-sm text-ink/70">{s.summary}</p>
                <div className="flex items-center justify-between">
                  <span className="chip">{t("landing.price")}: {s.price.amount.toLocaleString("ru-RU")} {s.price.currency}</span>
                  <Link href={`/start?country=${pack.country}`} className="btn-primary">{t("nav.start")}</Link>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <form onSubmit={joinWaitlist} className="card max-w-xl space-y-3">
            <h3 className="font-semibold">{t("landing.waitlistTitle")}</h3>
            <p className="text-sm text-ink/70">{t("landing.waitlistText")}</p>
            {sent ? (
              <p className="text-sm font-medium text-brand">{t("landing.waitlistDone")}</p>
            ) : (
              <>
                <input className="input" required minLength={3} placeholder={t("landing.waitlistContact")} value={contact} onChange={(e) => setContact(e.target.value)} />
                <textarea className="input" rows={3} placeholder={t("landing.waitlistProblem")} value={problem} onChange={(e) => setProblem(e.target.value)} />
                <button className="btn-primary" type="submit">{t("landing.waitlistSend")}</button>
                {error && <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-red-700">{error}</p>}
              </>
            )}
          </form>
        )}
      </section>

      <Trust />
    </div>
  );
}
