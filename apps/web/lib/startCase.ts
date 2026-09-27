"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, errorText, publicApi, type CaseView, type Emergency, type Reply } from "@/lib/api";
import type { Lang } from "@/lib/i18n";

/**
 * Start a case from free text: emergency check first (numbers before any intake), then create the case
 * and open it. Shared by the home page and /start.
 */
export function useStartCase(lang: Lang) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [emergency, setEmergency] = useState<Emergency | null>(null);

  async function start(text: string, { country = "KZ", skipTriage = false, religiousPath = false } = {}) {
    setBusy(true);
    setError(null);
    try {
      if (!skipTriage) {
        const tri = await publicApi<{ emergency: boolean; message: string; numbers: Emergency["numbers"] }>(
          "/v1/triage", { method: "POST", body: JSON.stringify({ text, country, language: lang }) });
        if (tri.emergency) {
          setEmergency({ message: tri.message, numbers: tri.numbers });
          setBusy(false);
          return;
        }
      }
      const out = await api<{ case: CaseView; reply: Reply }>("/v1/cases", {
        method: "POST",
        body: JSON.stringify({ text, language: lang, country, religious_path: religiousPath }),
      });
      try {
        sessionStorage.setItem(`konsilier.reply.${out.case.id}`, JSON.stringify(out.reply));
      } catch {}
      router.push(`/case/${out.case.id}`);
    } catch (err) {
      setError(errorText(err));
      setBusy(false);
    }
  }

  return { start, busy, error, emergency, dismissEmergency: () => setEmergency(null) };
}
