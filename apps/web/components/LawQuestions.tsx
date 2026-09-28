"use client";

import { useEffect, useState } from "react";
import { Alert, Badge, Button, Icon } from "@/components/ui";
import { ApiError, api, errorText } from "@/lib/api";
import { useT } from "@/lib/i18n";

type Norm = { act: string; act_code: string; article: string; title: string; quote: string; url: string };
type Answer = {
  id: string; question: string; created_at: string; answer: string; steps: string[]; norms: Norm[];
  unverified: number; needs_lawyer: boolean; confidence: "high" | "medium" | "low";
};

/** Ask a legal question about the case; the answer cites the articles the agent read on the official portal. */
export function LawQuestions({ caseId }: { caseId: string }) {
  const t = useT();
  const [items, setItems] = useState<Answer[]>([]);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<Answer[]>(`/v1/cases/${caseId}/questions`).then(setItems).catch(() => setItems([]));
  }, [caseId]);

  const ask = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      const a = await api<Answer>(`/v1/cases/${caseId}/questions`, { method: "POST", body: JSON.stringify({ question: q }) });
      setItems((xs) => [a, ...xs]);
      setQ("");
    } catch (err) {
      const key = err instanceof ApiError && err.code ? `law.errors.${err.code}` : "";
      setError(key && t(key) !== key ? t(key) : errorText(err));
    } finally { setBusy(false); }
  };

  return (
    <section aria-labelledby="law-q" className="card space-y-4">
      <div className="space-y-1">
        <h2 id="law-q" className="font-semibold">{t("law.title")}</h2>
        <p className="text-sm text-muted">{t("law.lead")}</p>
      </div>
      <form onSubmit={ask} className="space-y-2">
        <label className="sr-only" htmlFor="law-q-input">{t("law.title")}</label>
        <textarea id="law-q-input" className="input min-h-20" value={q} onChange={(e) => setQ(e.target.value)}
          placeholder={t("law.placeholder")} maxLength={2000} />
        <div className="flex flex-wrap items-center gap-3">
          <Button disabled={busy || q.trim().length < 5} icon={busy ? "spinner" : "send"}>{busy ? t("law.busy") : t("law.ask")}</Button>
          {busy && <span className="text-xs text-muted" role="status">{t("law.busyHint")}</span>}
        </div>
      </form>
      {error && <Alert tone="danger" role="alert">{error}</Alert>}

      {items.map((a) => (
        <article key={a.id} className="space-y-3 border-t border-line pt-4 text-sm">
          <p className="font-medium">«{a.question}»</p>
          {a.needs_lawyer
            ? <Alert tone="warning">{t("law.needsLawyer")}</Alert>
            : <Badge tone="brand" icon="shieldCheck">{t("law.verified")}</Badge>}
          <p className="whitespace-pre-line">{a.answer}</p>
          {a.steps.length > 0 && (
            <ol className="list-inside list-decimal space-y-1">{a.steps.map((s, i) => <li key={i}>{s}</li>)}</ol>
          )}
          {a.norms.length > 0 && (
            <div className="space-y-2">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted">{t("law.norms")}</p>
              {a.norms.map((n) => (
                <blockquote key={`${n.act_code}-${n.article}`} className="space-y-1 rounded-xl bg-sand p-3">
                  <p className="font-medium">{t("law.article", { n: n.article })}{n.title ? `. ${n.title}` : ""}</p>
                  <p className="text-xs text-muted">{n.act}</p>
                  <p className="italic">«{n.quote}»</p>
                  <a className="link inline-flex items-center gap-1 text-xs" href={n.url} target="_blank" rel="noopener noreferrer">
                    <Icon name="arrowRight" size={14} className="rtl:rotate-180" />{t("law.source")}
                  </a>
                </blockquote>
              ))}
            </div>
          )}
          {a.unverified > 0 && <p className="text-xs text-muted">{t("law.dropped", { n: a.unverified })}</p>}
        </article>
      ))}
      <p className="text-xs text-muted">{t("law.disclaimer")}</p>
    </section>
  );
}
