"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, type CaseView, type Reply, errorText } from "@/lib/api";
import { useLang, useT } from "@/lib/i18n";

export default function StartPage() {
  const t = useT();
  const { lang } = useLang();
  const router = useRouter();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const out = await api<{ case: CaseView; reply: Reply }>("/v1/cases", {
        method: "POST",
        body: JSON.stringify({ text, language: lang, country: new URLSearchParams(window.location.search).get("country") ?? "KZ" }),
      });
      sessionStorage.setItem(`konsilier.reply.${out.case.id}`, out.reply.message);
      router.push(`/case/${out.case.id}`);
    } catch (err) {
      setError(errorText(err));
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="mx-auto max-w-2xl space-y-4">
      <h1 className="text-3xl font-bold">{t("start.title")}</h1>
      <textarea
        className="input min-h-40 text-base"
        required
        minLength={10}
        placeholder={t("start.placeholder")}
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
      <button className="btn-primary w-full py-3 text-base sm:w-auto" disabled={busy}>{busy ? t("start.busy") : t("start.submit")}</button>
      {error && <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-red-700">{error}</p>}
      <p className="text-xs text-ink/50">{t("landing.disclaimer")}</p>
    </form>
  );
}

