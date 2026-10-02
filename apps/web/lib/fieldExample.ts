/** The example shown in an empty field of the form before payment («12.09.2026», «г. Алматы, ул. Абая, 10»), by the
 *  field's type, else its name — the same keys as the draft's (draft.example.*). PM 02.10: the form's empty fields
 *  gave no hint and «10 сентября» came back as an error. */
export function exampleKey(f: { field: string; type: string; pattern?: string | null }): string | null {
  if (f.type === "date" || f.type === "date_future") return "date";
  if (f.type === "money" || f.type === "email" || f.type === "phone") return f.type;
  if (f.pattern) return "id";
  if (/address/.test(f.field)) return "address";
  if (/goods|item|product|service|subject|description/.test(f.field)) return "goods";
  if (/applicant|full_name|fio/.test(f.field)) return "name";
  if (/seller|respondent|employer|bank|company|organization|party|counterparty|_name$/.test(f.field)) return "party";
  return null;
}

/** Digits only, the dots put in as they are typed: «12092026» → «12.09.2026» (iOS's numeric keypad has no dot). */
export function dateMask(raw: string): string {
  const d = raw.replace(/\D/g, "").slice(0, 8);
  return [d.slice(0, 2), d.slice(2, 4), d.slice(4)].filter(Boolean).join(".");
}
