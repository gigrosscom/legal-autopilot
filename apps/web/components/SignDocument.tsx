"use client";

import { useEffect, useState } from "react";
import { Button, Icon } from "@/components/ui";
import { ApiError, api, downloadFile, errorText, type AuthMethods, type DocSignature } from "@/lib/api";
import { useLang, useT } from "@/lib/i18n";
import { NcaLayerError, signDocument } from "@/lib/ncalayer";

type EgovStart = { session_id: string; qr: string; links: { egov_mobile: string; egov_business: string } };

/** Sign a prepared document with ЭЦП: NCALayer on a computer or eGov Mobile by QR; shows existing signatures. */
export function SignDocument({ base, fileBase, initial, canSign, lead, onSigned, unavailable }: {
  /** API path of the thing being signed: /v1/cases/{id}/actions/{id} or /v1/agreements/{id} */
  base: string; fileBase: string; initial: DocSignature[];
  /** show the sign buttons (default: only while nothing is signed) */
  canSign?: boolean; lead?: string; onSigned?: (s: DocSignature) => void;
  /** shown instead of nothing when no signing method is available on this server */
  unavailable?: string;
}) {
  const t = useT();
  const { lang } = useLang();
  const [methods, setMethods] = useState<AuthMethods | null>(null);
  const [signatures, setSignatures] = useState<DocSignature[]>(initial);
  const [busy, setBusy] = useState(false);
  const [egov, setEgov] = useState<{ start: EgovStart; svg: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<AuthMethods>("/v1/auth/methods").then(setMethods)
      .catch(() => setMethods({ ecp: false, egov: false } as AuthMethods)); // unreachable → treat as unavailable
  }, []);

  const explain = (e: unknown) => {
    if (e instanceof NcaLayerError) return t(`account.ecp.${e.kind}`);
    if (e instanceof ApiError && e.code) {
      for (const key of [`sign.errors.${e.code}`, `account.errors.${e.code}`]) {
        const text = t(key);
        if (text !== key) return text;
      }
    }
    return errorText(e);
  };

  const withNcaLayer = async () => {
    setBusy(true); setError(null);
    try {
      const s = await api<{ session_id: string; data: string }>(`${base}/sign/start`, {
        method: "POST", body: JSON.stringify({ method: "ncalayer" }) });
      const cms = await signDocument(s.data, lang);
      const r = await api<{ signature: DocSignature }>(`${base}/sign`, {
        method: "POST", body: JSON.stringify({ session_id: s.session_id, cms }) });
      setSignatures((x) => [...x, r.signature]);
      onSigned?.(r.signature);
    } catch (e) { setError(explain(e)); } finally { setBusy(false); }
  };

  const withEgov = async () => {
    setError(null);
    try {
      const s = await api<EgovStart>(`${base}/sign/start`, { method: "POST", body: JSON.stringify({ method: "egov" }) });
      const QR = (await import("qrcode")).default;
      setEgov({ start: s, svg: await QR.toString(s.qr, { type: "svg", margin: 1, errorCorrectionLevel: "M" }) });
    } catch (e) { setError(explain(e)); }
  };

  useEffect(() => {
    if (!egov) return;
    const id = setInterval(async () => {
      try {
        const r = await api<{ status: string; signature?: DocSignature; code?: string }>(`${base}/sign/status/${egov.start.session_id}`);
        if (r.status === "done" && r.signature) {
          setSignatures((x) => [...x, r.signature!]);
          onSigned?.(r.signature);
          setEgov(null);
        }
        else if (r.status === "failed") {
          const key = `sign.errors.${r.code}`;
          setError(t(key) !== key ? t(key) : t("account.errors.invalid_signature"));
          setEgov(null);
        }
        else if (r.status === "expired") { setError(t("account.egov.expired")); setEgov(null); }
      } catch { /* slow network: keep polling */ }
    }, 2500);
    return () => clearInterval(id);
  }, [egov, base, t, onSigned]);

  const canNca = methods?.ecp ?? false;
  const canEgov = methods?.egov ?? false;
  const showButtons = (canSign ?? !signatures.length) && (canNca || canEgov);
  if (!signatures.length && !showButtons) {
    return unavailable && methods !== null
      ? <p className="rounded-xl border border-line p-3 text-sm text-muted">{unavailable}</p> : null;
  }

  return (
    <div className="space-y-2 rounded-xl border border-line p-3 text-sm">
      {signatures.map((s) => (
        <div key={s.id} className="flex flex-wrap items-center gap-2">
          <Icon name="shieldCheck" size={18} className="text-brand" />
          <span>{t(s.role === "lawyer" ? "sign.signedByLawyer" : "sign.signedBy", { name: s.signer_name ?? "", id: s.display })}</span>
          <span className="text-muted">{new Date(s.signed_at).toLocaleString(lang === "ar" ? "ar" : "ru-RU")}</span>
          <button type="button" className="link" onClick={() => downloadFile(`${base}/signatures/${s.id}.cms`, `${fileBase}.${s.format}.cms`)}>
            {t("sign.download")}
          </button>
        </div>
      ))}
      {signatures.length > 0 && <p className="text-xs text-muted">{t("sign.verifyHint")}</p>}
      {showButtons && !egov && (
        <div className="space-y-2">
          <p className="text-muted">{lead ?? t("sign.lead")}</p>
          <div className="flex flex-wrap gap-2">
            {canNca && <Button variant="secondary" icon={busy ? "spinner" : "key"} disabled={busy} onClick={withNcaLayer}>
              {busy ? t("account.ecp.waiting") : t("sign.ncalayer")}</Button>}
            {canEgov && <Button variant="secondary" icon="qr" onClick={withEgov}>{t("sign.egov")}</Button>}
          </div>
        </div>
      )}
      {egov && (
        <div className="grid gap-3 sm:grid-cols-[160px_1fr] sm:items-center">
          <div role="img" aria-label={t("account.egov.qrAlt")} className="mx-auto w-40 rounded-xl bg-white p-2 sm:mx-0"
            dangerouslySetInnerHTML={{ __html: egov.svg }} />
          <div className="space-y-2 text-muted">
            <p>{t("account.egov.scan")}</p>
            <div className="flex flex-wrap gap-2">
              <a className="btn-ghost" href={egov.start.links.egov_mobile}>eGov Mobile</a>
              <a className="btn-ghost" href={egov.start.links.egov_business}>eGov Business</a>
            </div>
            <p className="flex items-center gap-2" role="status"><Icon name="spinner" size={16} />{t("account.egov.waiting")}</p>
          </div>
        </div>
      )}
      {error && <p role="alert" className="text-danger">{error}</p>}
    </div>
  );
}
