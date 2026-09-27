"use client";

import { useEffect, useRef, useState } from "react";
import { Badge, Icon } from "@/components/ui";
import { api, errorText } from "@/lib/api";
import { useT } from "@/lib/i18n";

type GovService = { id: string; title: string; url: string; provider: string; auth: "ecp" | "ecp_or_egov_mobile" | "none"; note: string | null };

/** Certificates the person gets themselves on egov.kz (with their own ЭЦП), then uploads here as evidence. */
export function GovServices({ caseId }: { caseId: string }) {
  const t = useT();
  const [items, setItems] = useState<GovService[]>([]);
  const [uploaded, setUploaded] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const inputs = useRef<Record<string, HTMLInputElement | null>>({});

  useEffect(() => {
    api<GovService[]>(`/v1/cases/${caseId}/gov-services`).then(setItems).catch(() => setItems([]));
  }, [caseId]);

  const upload = async (g: GovService, file: File) => {
    setBusy(g.id); setError(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("kind", "gov_certificate");
      await api(`/v1/cases/${caseId}/evidence`, { method: "POST", body: fd });
      setUploaded((u) => ({ ...u, [g.id]: file.name }));
    } catch (e) { setError(errorText(e)); } finally { setBusy(null); }
  };

  if (!items.length) return null;
  return (
    <section aria-labelledby="gov-services" className="card space-y-3">
      <div className="space-y-1">
        <h2 id="gov-services" className="font-semibold">{t("gov.title")}</h2>
        <p className="text-sm text-muted">{t("gov.lead")}</p>
      </div>
      <ul className="space-y-3">
        {items.map((g) => (
          <li key={g.id} className="space-y-2 rounded-xl border border-line p-3 text-sm">
            <div className="flex flex-wrap items-start gap-2">
              <span className="me-auto font-medium">{g.title}</span>
              {g.auth === "none" ? <Badge tone="brand">{t("gov.open")}</Badge>
                : <Badge icon="key">{t(g.auth === "ecp" ? "gov.ecpOnly" : "gov.needsEcp")}</Badge>}
            </div>
            <p className="text-xs text-muted">{g.provider}{g.note ? ` · ${g.note}` : ""}</p>
            <div className="flex flex-wrap items-center gap-2">
              <a className="btn-ghost" href={g.url} target="_blank" rel="noopener noreferrer">
                <Icon name="arrowRight" size={16} className="rtl:rotate-180" />{t("gov.get")}
              </a>
              <input ref={(el) => { inputs.current[g.id] = el; }} type="file" accept=".pdf,image/*" className="sr-only"
                aria-label={t("gov.upload")} onChange={(e) => e.target.files?.[0] && upload(g, e.target.files[0])} />
              <button type="button" className="btn-ghost" disabled={busy === g.id} onClick={() => inputs.current[g.id]?.click()}>
                <Icon name={busy === g.id ? "spinner" : "upload"} size={16} />{t("gov.upload")}
              </button>
              {uploaded[g.id] && <span className="flex items-center gap-1 text-brand"><Icon name="checkCircle" size={16} />{t("gov.uploaded")}</span>}
            </div>
          </li>
        ))}
      </ul>
      {error && <p role="alert" className="text-sm text-danger">{error}</p>}
      <p className="text-xs text-muted">{t("gov.disclaimer")}</p>
    </section>
  );
}
