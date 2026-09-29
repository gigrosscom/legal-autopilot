"use client";

import en from "@/lib/legal/terms.en";
import kk from "@/lib/legal/terms.kk";
import ru, { TERMS_VERSION, type LegalDoc } from "@/lib/legal/terms";
import { useLang, useT } from "@/lib/i18n";

const DOCS: Record<string, LegalDoc> = { ru, kk, en };

/** Пользовательское соглашение. Russian and Kazakh are the languages of the agreement; others read English. */
export default function TermsPage() {
  const t = useT();
  const { lang } = useLang();
  const doc = DOCS[lang] ?? en;
  return (
    <article className="mx-auto max-w-3xl space-y-8">
      <header className="space-y-2">
        <h1 className="text-3xl font-semibold tracking-tight">{doc.title}</h1>
        <p className="text-sm text-muted">{doc.edition} · {t("legal.version")} {TERMS_VERSION}</p>
        {!DOCS[lang] && <p className="text-sm text-muted">{t("legal.languageNote")}</p>}
      </header>
      <section className="card space-y-3 border-brand" aria-labelledby="summary">
        <h2 id="summary" className="text-lg font-semibold">{doc.summaryTitle}</h2>
        <ul className="space-y-2">
          {doc.summary.map((s) => <li key={s} className="flex gap-2"><span aria-hidden className="text-brand">•</span><span>{s}</span></li>)}
        </ul>
      </section>
      {doc.sections.map((s) => (
        <section key={s.h} className="space-y-2">
          <h2 className="text-lg font-semibold">{s.h}</h2>
          {s.p.map((p) => <p key={p} className="text-pretty leading-relaxed">{p}</p>)}
        </section>
      ))}
    </article>
  );
}
