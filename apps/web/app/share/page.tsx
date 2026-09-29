"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Alert, Button, Icon } from "@/components/ui";
import { api, errorText, type CaseView } from "@/lib/api";
import { useT } from "@/lib/i18n";
import { clearShared, sharedFiles } from "@/lib/share";

const NEW = "new";

function size(bytes: number): string {
  return bytes >= 1_048_576 ? `${(bytes / 1_048_576).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

/**
 * Files shared to the installed app from another app (Android: «Поделиться» → Консильéр). public/sw.js keeps them;
 * here the person picks the case (or starts a new one) and they are uploaded as the case's documents.
 */
export default function SharePage() {
  const t = useT();
  const router = useRouter();
  const [files, setFiles] = useState<File[] | null>(null);
  const [cases, setCases] = useState<CaseView[] | null>(null);
  const [target, setTarget] = useState<string>(NEW);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    sharedFiles().then(setFiles);
    let signed = false;
    try { signed = !!localStorage.getItem("konsilier.token"); } catch {}
    if (!signed) { setCases([]); return; }  // no account on this device yet: only a new case
    api<CaseView[]>("/v1/cases").then((cs) => {
      setCases(cs);
      if (cs.length) setTarget(cs[0].id);
    }).catch((e) => { setCases([]); setError(errorText(e)); });
  }, []);

  const title = (c: CaseView) => c.scenario?.title ?? c.coverage?.dispute?.title ?? t("case.untitled");

  const attach = async () => {
    if (!files?.length) return;
    if (target === NEW) { router.push("/start?shared=1"); return; }
    setBusy(true); setError(null); setDone(0);
    try {
      for (const [i, file] of files.entries()) {
        const form = new FormData();
        form.append("file", file);
        form.append("kind", "other");
        await api(`/v1/cases/${target}/evidence`, { method: "POST", body: form });
        setDone(i + 1);
      }
      await clearShared();
      router.push(`/case/${target}`);
    } catch (e) {
      setError(errorText(e));
      setBusy(false);
    }
  };

  const cancel = async () => { await clearShared(); router.push("/cases"); };

  if (files === null) return <p className="text-muted">{t("common.loading")}</p>;
  if (files.length === 0) {
    return (
      <div className="card mx-auto max-w-md space-y-3 text-center">
        <Icon name="paperclip" size={32} className="mx-auto text-muted" />
        <h1 className="text-xl font-semibold">{t("share.emptyTitle")}</h1>
        <p className="text-sm text-muted">{t("share.emptyText")}</p>
        <Button href="/cases" variant="secondary">{t("nav.cases")}</Button>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div className="space-y-2">
        <p className="eyebrow">{t("share.eyebrow")}</p>
        <h1 className="text-3xl font-semibold tracking-tight">{t("share.title")}</h1>
        <p className="text-muted">{t("share.lead")}</p>
      </div>

      <ul className="divide-y divide-line rounded-2xl border border-line" aria-label={t("share.files", { n: files.length })}>
        {files.map((f, i) => (
          <li key={i} className="flex items-center gap-3 px-4 py-3 text-sm">
            <Icon name={f.type.startsWith("image/") ? "camera" : "document"} size={20} className="shrink-0 text-brand" />
            <span className="min-w-0 flex-1 truncate">{f.name}</span>
            <span className="shrink-0 text-muted tabular-nums" dir="ltr">{size(f.size)}</span>
            {busy && i < done && <Icon name="check" size={18} className="shrink-0 text-success" />}
          </li>
        ))}
      </ul>

      <fieldset className="space-y-2" disabled={busy}>
        <legend className="mb-2 font-semibold">{t("share.where")}</legend>
        <label className={`flex min-h-14 cursor-pointer items-center gap-3 rounded-2xl border px-4 ${target === NEW ? "border-brand bg-brand-50" : "border-line"}`}>
          <input type="radio" name="case" value={NEW} checked={target === NEW} onChange={() => setTarget(NEW)} className="h-5 w-5 accent-brand" />
          <Icon name="plus" size={20} className="text-brand" />
          <span className="flex-1 font-medium">{t("share.newCase")}</span>
        </label>
        {cases === null && <p className="text-sm text-muted">{t("common.loading")}</p>}
        {cases?.map((c) => (
          <label key={c.id} className={`flex min-h-14 cursor-pointer items-center gap-3 rounded-2xl border px-4 py-2 ${target === c.id ? "border-brand bg-brand-50" : "border-line"}`}>
            <input type="radio" name="case" value={c.id} checked={target === c.id} onChange={() => setTarget(c.id)} className="h-5 w-5 accent-brand" />
            <Icon name="folder" size={20} className="text-muted" />
            <span className="min-w-0 flex-1">
              <span className="block truncate font-medium">{title(c)}</span>
              <span className="block text-xs text-muted">{c.status_label}</span>
            </span>
          </label>
        ))}
        {cases?.length === 0 && (
          <p className="text-sm text-muted">{t("share.noCases")} <Link href="/account?next=/share" className="link">{t("share.signIn")}</Link></p>
        )}
      </fieldset>

      {error && <Alert tone="danger" role="alert">{error}</Alert>}

      <div className="flex flex-wrap gap-3">
        <Button onClick={attach} disabled={busy} icon={busy ? "spinner" : "upload"} size="lg">
          {busy ? t("share.uploading", { n: done, total: files.length }) : target === NEW ? t("share.startCase") : t("share.attach")}
        </Button>
        <Button onClick={cancel} disabled={busy} variant="secondary">{t("app.cancel")}</Button>
      </div>
    </div>
  );
}
