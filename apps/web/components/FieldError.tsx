"use client";

import { useCallback } from "react";
import { useT } from "@/lib/i18n";

/** Text for a field error code: `formErrors.<field>_<code>` if there is one, else `formErrors.<code>`. */
export function useFieldErrorText() {
  const t = useT();
  return useCallback((field: string, code: string) => {
    const specific = `formErrors.${field}_${code}`;
    const s = t(specific);
    if (s !== specific) return s;
    const generic = `formErrors.${code}`;
    const g = t(generic);
    return g !== generic ? g : t("formErrors.invalid");
  }, [t]);
}

/** The message under a field; its id is referenced by the field's aria-describedby. */
export function FieldError({ id, field, code }: { id: string; field: string; code?: string | null }) {
  const text = useFieldErrorText();
  if (!code) return null;
  return <p id={id} className="mt-1 text-sm text-danger">{text(field, code)}</p>;
}
