"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError, api, errorText, type CaseView } from "@/lib/api";
import { Alert, Button, Icon } from "@/components/ui";
import { useT } from "@/lib/i18n";

const KNOWN = ["pattern", "address", "date", "date_future", "money", "email", "phone"];
type Blank = { field: string; label: string; type: string; pattern: string | null };
type Draft = { title: string; visible: string; hidden: string; paid: boolean; blanks: Blank[] };

/** PM 01.10: the document's draft before payment — the start readable, the rest blurred, and the blanks the person
 * can fill right here (what the interview did not ask, «не помню», a foreign seller without a BIN). */
export function DraftPreview({ caseId, version, onCase }: { caseId: string; version: string; onCase: (c: CaseView) => void }) {
  const t = useT();
  const [d, setD] = useState<Draft | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => api<Draft>(`/v1/cases/${caseId}/draft`).then(setD).catch(() => setD(null)), [caseId]);
  useEffect(() => { load(); }, [load, version]);

  async function save() {
    setBusy(true); setError(null); setErrors({});
    try {
      const out = await api<{ case: CaseView }>(`/v1/cases/${caseId}/facts`, { method: "POST", body: JSON.stringify({ values }) });
      setValues({});
      onCase(out.case);
      await load();
    } catch (e) {
      const fields = e instanceof ApiError ? (e.detail as { fields?: Record<string, string> })?.fields : undefined;
      if (fields) setErrors(fields); else setError(errorText(e));
    } finally { setBusy(false); }
  }

  if (!d) return null;
  const filled = Object.values(values).some((v) => v.trim());
  return (
    <section aria-labelledby="draft-title" className="card space-y-3">
      <h2 id="draft-title" className="flex items-center gap-2 text-lg font-semibold">
        <Icon name="document" className="text-brand" />{t("draft.title")}: {d.title}
      </h2>
      {!d.paid && <p className="text-sm text-muted">{t("draft.lead")}</p>}
      <div className="relative max-h-[28rem] overflow-hidden rounded-xl bg-sand p-4 text-[15px] leading-relaxed">
        <p className="whitespace-pre-wrap">{d.visible}</p>
        {d.hidden && (
          <>
            <p aria-hidden className="select-none whitespace-pre-wrap blur-[5px]">{d.hidden}</p>
            <p className="absolute inset-x-0 bottom-0 flex items-center justify-center gap-2 bg-gradient-to-t from-sand via-sand/90 to-transparent pt-16 pb-4 text-sm font-semibold">
              <Icon name="lock" size={18} />{t("draft.locked")}
            </p>
          </>
        )}
      </div>
      {d.blanks.length > 0 && (
        <div className="space-y-2">
          <p className="font-semibold">{t("draft.blanks")}</p>
          {d.blanks.map((b) => (
            <label key={b.field} className="block text-sm">
              {b.label}
              <input className={`input mt-1 ${errors[b.field] ? "border-danger" : ""}`} value={values[b.field] ?? ""}
                type={b.type === "date" ? "date" : b.type === "email" ? "email" : "text"}
                inputMode={b.type === "money" || b.pattern ? "numeric" : undefined}
                onChange={(e) => setValues((v) => ({ ...v, [b.field]: e.target.value }))} aria-invalid={!!errors[b.field]} />
              {errors[b.field] && <span className="text-danger">{t(`draft.error.${KNOWN.includes(errors[b.field]) ? errors[b.field] : "generic"}`)}</span>}
            </label>
          ))}
          <Button className="w-full" variant="secondary" disabled={busy || !filled} onClick={save}>{t("draft.save")}</Button>
        </div>
      )}
      {error && <Alert tone="danger" role="alert">{error}</Alert>}
    </section>
  );
}
