"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError, api, errorText, type CaseView } from "@/lib/api";
import { Alert, Button, Icon } from "@/components/ui";
import { useT } from "@/lib/i18n";

const KNOWN = ["pattern", "address", "date", "date_future", "money", "email", "phone"];
type Blank = { field: string; label: string; type: string; pattern: string | null };
type Draft = { title: string; visible: string; hidden: string; paid: boolean; blanks: Blank[] };

/** The example in an empty field («12.09.2026», «45 000 ₸», «ТОО «Магазин»») — by the field's type, else its name. */
function example(b: Blank): string | null {
  if (b.type === "date" || b.type === "date_future") return "date";
  if (b.type === "money" || b.type === "email" || b.type === "phone") return b.type;
  if (b.pattern) return "id";
  if (/address/.test(b.field)) return "address";
  if (/goods|item|product|service|subject|description/.test(b.field)) return "goods";
  if (/applicant|full_name|fio/.test(b.field)) return "name";
  if (/seller|respondent|employer|bank|company|organization|party|counterparty|_name$/.test(b.field)) return "party";
  return null;
}

/** Digits only, the dots put in as they are typed: «12092026» → «12.09.2026» (the numeric keypad has no dot on iOS;
 *  a native date field is wider than the card there and shows no example). */
function dateMask(raw: string): string {
  const d = raw.replace(/\D/g, "").slice(0, 8);
  return [d.slice(0, 2), d.slice(2, 4), d.slice(4)].filter(Boolean).join(".");
}

/** PM 01.10: the document's draft before payment — the start readable, the rest blurred, and the blanks the person
 * can fill right here (what the interview did not ask, «не помню», a foreign seller without a BIN). */
// PM 02.10: the applicant typed their name and address here and was asked again in «Оплата → Ваши данные» — the
// field was typed but «Сохранить в документ» not pressed. Each field is now saved as soon as it is left; the payment
// waits for that save (draftSaved) before it asks the server which data is still missing.
let pendingSave: Promise<unknown> = Promise.resolve();
export const draftSaved = () => pendingSave.catch(() => undefined);

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

  // a field left with a value is saved at once (a wrong format is shown under it and asked again on «Сохранить»)
  function saveField(field: string) {
    const value = (values[field] ?? "").trim();
    if (!value) return;
    pendingSave = pendingSave.then(async () => {
      try {
        const out = await api<{ case: CaseView }>(`/v1/cases/${caseId}/facts`, { method: "POST", body: JSON.stringify({ values: { [field]: value } }) });
        setValues((v) => { const { [field]: _, ...rest } = v; return rest; });
        setErrors((x) => { const { [field]: _, ...rest } = x; return rest; });
        onCase(out.case);
      } catch (e) {
        const fields = e instanceof ApiError ? (e.detail as { fields?: Record<string, string> })?.fields : undefined;
        if (fields) setErrors((x) => ({ ...x, ...fields }));
      }
    });
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
          {d.blanks.map((b) => {
            const date = b.type === "date" || b.type === "date_future";
            const money = b.type === "money";
            return (
              <label key={b.field} className="block text-sm">
                {b.label}
                <span className="relative mt-1 block">
                  <input className={`input min-h-12 min-w-0 appearance-none ${money ? "pe-9" : ""} ${errors[b.field] ? "border-danger" : ""}`}
                    value={values[b.field] ?? ""} placeholder={example(b) ? t(`draft.example.${example(b)}`) : undefined}
                    type={b.type === "email" ? "email" : b.type === "phone" ? "tel" : "text"}
                    inputMode={date || money || b.pattern ? "numeric" : b.type === "phone" ? "tel" : b.type === "email" ? "email" : undefined}
                    autoComplete="off" enterKeyHint="next"
                    onChange={(e) => setValues((v) => ({ ...v, [b.field]: date ? dateMask(e.target.value) : e.target.value }))}
                    onBlur={() => saveField(b.field)}
                    aria-invalid={!!errors[b.field]} />
                  {money && <span aria-hidden className="pointer-events-none absolute inset-y-0 end-3 flex items-center text-base text-muted">₸</span>}
                </span>
                {errors[b.field] && <span className="text-danger">{t(`draft.error.${KNOWN.includes(errors[b.field]) ? errors[b.field] : "generic"}`)}</span>}
              </label>
            );
          })}
          <Button className="w-full" variant="secondary" disabled={busy || !filled} onClick={save}>{t("draft.save")}</Button>
        </div>
      )}
      {error && <Alert tone="danger" role="alert">{error}</Alert>}
    </section>
  );
}
