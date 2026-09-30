"use client";

import { useEffect, useState } from "react";
import { ForLawyersView } from "@/components/ForLawyersView";
import { api } from "@/lib/api";
import { useT } from "@/lib/i18n";

/** «Юрист по кнопке»: the owner's private link for pilot lawyers (/join?t=…, made in /ops). The public page for
 * lawyers stays hidden; only a valid link opens the application form. */
export default function Join() {
  const t = useT();
  const [token, setToken] = useState<string | null>(null);
  const [valid, setValid] = useState<boolean | null>(null);

  useEffect(() => {
    const tk = new URLSearchParams(window.location.search).get("t") ?? "";
    setToken(tk);
    if (!tk) { setValid(false); return; }
    api<{ valid: boolean }>(`/v1/lawyer-invite/${encodeURIComponent(tk)}`)
      .then((r) => setValid(r.valid)).catch(() => setValid(false));
  }, []);

  if (valid === null) return <p className="py-16 text-center text-muted">{t("pilot.inviteChecking")}</p>;
  if (!valid || !token) return <p role="alert" className="mx-auto max-w-xl py-16 text-center">{t("pilot.inviteInvalid")}</p>;
  return <ForLawyersView invite={token} />;
}
