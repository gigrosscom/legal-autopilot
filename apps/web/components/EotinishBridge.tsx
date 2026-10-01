"use client";

import { useEffect, useState, type ReactNode } from "react";
import { FilePicker } from "@/components/FilePicker";
import { Alert, Button, Icon } from "@/components/ui";
import { ApiError, api, downloadFile, errorText, type CaseAction, type CaseView, type EotinishGuide, type PortalProof } from "@/lib/api";
import { useLang, useT } from "@/lib/i18n";

/** Today in the person's own calendar, as YYYY-MM-DD (the value of a date input). */
function today(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

const ERR_CODES = ["bad_number", "date_in_future", "date_before_document", "bad_receipt", "already_filed"];

/** Manual eOtinish bridge (owner's decisions 01.10.2026): the person files the appeal on eotinish.kz themselves, in
 *  their own name. We show what to pick in the portal's form, the ready text and the file. Then («3 клика») the
 *  person attaches the portal's confirmation — screenshot, PDF or the notification e-mail/SMS text — and we read the
 *  appeal number and date for a one-tap confirmation; typing them is only the fallback when reading fails. The
 *  response deadline and reminders run from that date. */
export function EotinishBridge({ caseId, a, onCase, startOpen = false }: {
  caseId: string; a: CaseAction; onCase?: (c: CaseView) => void;
  /** opened from the send wizard's portal step: show the steps at once */
  startOpen?: boolean;
}) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const [guide, setGuide] = useState<EotinishGuide | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [number, setNumber] = useState("");
  const [date, setDate] = useState(today());
  const [proof, setProof] = useState<PortalProof | null>(null);
  const [manual, setManual] = useState(false);
  const [paste, setPaste] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const target = a.appeal_portal;
  useEffect(() => {
    if (startOpen && target) void start();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [startOpen]);
  if (!target) return null;

  const start = async () => {
    setOpen(true);
    if (guide) return;
    setLoading(true);
    setError(null);
    try { setGuide(await api<EotinishGuide>(`/v1/cases/${caseId}/actions/${a.id}/portal-filing`)); }
    catch (e) { setError(errorText(e)); }
    finally { setLoading(false); }
  };

  const fmt = a.has_pdf || guide?.has_pdf ? "pdf" : "docx";
  const file = `/v1/cases/${caseId}/actions/${a.id}/document?format=${fmt}`;

  // «3 клика»: the confirmation (screenshot, PDF, notification e-mail or its text) is read for the number and date
  const readProof = async (file: File | null, text?: string) => {
    setBusy(true);
    setError(null);
    try {
      const form = new FormData();
      if (file) form.append("file", file);
      else form.append("text", text ?? "");
      const got = await api<PortalProof>(`/v1/cases/${caseId}/actions/${a.id}/portal-filing/proof`, { method: "POST", body: form });
      setProof(got);
      setNumber(got.number ?? "");
      setDate(got.filed_on ?? today());
      setManual(!got.found);
      setPaste(null);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  };

  const confirm = async (n: string, d: string) => {
    setBusy(true);
    setError(null);
    try {
      const out = await api<{ case: CaseView }>(`/v1/cases/${caseId}/actions/${a.id}/portal-filing`, {
        method: "POST", body: JSON.stringify({ number: n, filed_on: d, receipt_evidence_id: proof?.evidence_id ?? null }) });
      onCase?.(out.case);
      setOpen(false);
    } catch (err) {
      const code = err instanceof ApiError ? err.code : null;
      setError(code && ERR_CODES.includes(code) ? t(`eotinish.err.${code}`) : errorText(err));
      setManual(true);
    } finally {
      setBusy(false);
    }
  };
  const submit = (e: React.FormEvent) => { e.preventDefault(); void confirm(number, date); };
  const shown = (iso: string) => new Date(`${iso}T12:00:00`).toLocaleDateString("ru-RU");

  const step = (i: number, title: string, body: ReactNode) => (
    <li className="flex gap-3">
      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-line bg-surface text-xs font-semibold text-ink">{i}</span>
      <div className="min-w-0 flex-1 space-y-2">
        <p className="text-sm font-semibold text-ink">{title}</p>
        {body}
      </div>
    </li>
  );
  const row = (label: string, value: ReactNode) => (
    <div>
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="break-words text-sm text-ink">{value}</dd>
    </div>
  );

  return (
    <section className="space-y-3 rounded-2xl border border-line bg-sand p-4" aria-labelledby={`eot-${a.id}`}>
      <div className="space-y-1">
        <h4 id={`eot-${a.id}`} className="flex items-center gap-2 font-semibold text-ink"><Icon name="landmark" size={18} />{t("eotinish.title")}</h4>
        <p className="text-xs text-muted">{t("eotinish.lead")}</p>
      </div>
      {!open && (
        <Button className="min-h-11 w-full sm:w-auto" icon="send" onClick={start}>{t("eotinish.cta")}</Button>
      )}
      {open && loading && <p className="flex items-center gap-2 text-sm text-muted"><Icon name="spinner" size={16} className="animate-spin" />{t("eotinish.loading")}</p>}
      {open && guide && (
        <ol className="space-y-4">
          {step(1, t("eotinish.s1"), (
            <>
              <dl className="space-y-2 rounded-xl bg-surface p-3">
                {guide.appeal_type && row(t("eotinish.appealType"), <b>{t(`eotinish.type.${guide.appeal_type}`)}</b>)}
                {row(t("eotinish.recipient"), (
                  <>
                    <b className="block">{guide.recipient || guide.body}</b>
                    {guide.recipient && guide.body && guide.recipient !== guide.body && <span className="block text-xs text-muted">{guide.body}</span>}
                  </>
                ))}
                {row(t("eotinish.category"), guide.category ? <b>{guide.category}</b> : <span className="text-muted">{t("eotinish.categoryAny")}</span>)}
              </dl>
              {!guide.verified && <p className="text-xs text-muted">{t("eotinish.unverified")}</p>}
            </>
          ))}
          {step(2, t("eotinish.s2"), (
            <>
              <textarea readOnly value={guide.text} rows={8} aria-label={t("eotinish.s2")}
                className="input w-full resize-y font-mono text-xs leading-relaxed" />
              <button type="button" className="btn-ghost min-h-10" onClick={async () => {
                try { await navigator.clipboard.writeText(guide.text); setCopied(true); setTimeout(() => setCopied(false), 2500); } catch {}
              }}>
                <Icon name={copied ? "check" : "copy"} size={16} />{copied ? t("eotinish.copied") : t("eotinish.copy")}
              </button>
            </>
          ))}
          {step(3, t("eotinish.s3"), (
            <button type="button" className="btn-ghost min-h-10" onClick={() => downloadFile(file, `${a.action_id}.${fmt}`)}>
              <Icon name="download" size={16} />{fmt === "pdf" ? t("eotinish.downloadPdf") : t("eotinish.downloadDocx")}
            </button>
          ))}
          {step(4, t("eotinish.s4"), (
            <>
              <a href={guide.portal} target="_blank" rel="noreferrer" className="btn-primary min-h-11 w-full sm:w-auto">
                {t("eotinish.open")}<Icon name="external" size={16} />
              </a>
              <p className="text-xs text-muted">{t("eotinish.how")}</p>
            </>
          ))}
          {step(5, t("eotinish.s5"), (
            <div className="space-y-3">
              {!proof && !manual && (
                <>
                  <p className="text-xs text-muted">{t("eotinish.proofLead")}</p>
                  <div className="flex flex-wrap items-center gap-2">
                    <FilePicker disabled={busy} onFile={(f) => void readProof(f)} attachLabel={t("eotinish.proofAttach")} />
                  </div>
                  {paste === null ? (
                    <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
                      <button type="button" className="link" onClick={() => setPaste("")}>{t("eotinish.proofPaste")}</button>
                      <button type="button" className="link" onClick={() => setManual(true)}>{t("eotinish.proofManual")}</button>
                    </div>
                  ) : (
                    <div className="space-y-2">
                      <textarea className="input w-full" rows={4} value={paste} aria-label={t("eotinish.proofPaste")}
                        placeholder={t("eotinish.proofPasteHint")} onChange={(e) => setPaste(e.target.value)} />
                      <Button type="button" variant="secondary" icon="sparkle" disabled={busy || !paste.trim()}
                        onClick={() => void readProof(null, paste)}>{t("eotinish.proofRead")}</Button>
                    </div>
                  )}
                  {busy && <p className="flex items-center gap-2 text-sm text-muted"><Icon name="spinner" size={16} className="animate-spin" />{t("eotinish.proofReading")}</p>}
                </>
              )}
              {proof?.found && !manual && (
                <div className="space-y-3 rounded-xl bg-surface p-3">
                  <p className="text-xs text-muted">{t("eotinish.proofFound")}</p>
                  <dl className="grid gap-2 text-sm sm:grid-cols-2">
                    <div><dt className="text-xs text-muted">{t("eotinish.number")}</dt><dd className="font-semibold tabular-nums">{proof.number}</dd></div>
                    <div><dt className="text-xs text-muted">{t("eotinish.date")}</dt><dd className="font-semibold tabular-nums">{shown(proof.filed_on!)}</dd></div>
                  </dl>
                  <div className="flex flex-wrap gap-2">
                    <Button type="button" className="min-h-11 flex-1" icon="check" disabled={busy}
                      onClick={() => void confirm(proof.number!, proof.filed_on!)}>{t("eotinish.proofConfirm")}</Button>
                    <Button type="button" variant="secondary" className="min-h-11" disabled={busy} onClick={() => setManual(true)}>{t("eotinish.proofEdit")}</Button>
                  </div>
                  <p className="text-xs text-muted">{t("eotinish.saveHint")}</p>
                </div>
              )}
              {manual && (
                <form className="space-y-3" onSubmit={submit}>
                  {proof && !proof.found && <Alert tone="info" icon="info">{t("eotinish.proofNotFound")}</Alert>}
                  <label className="block text-sm">
                    <span className="text-xs text-muted">{t("eotinish.number")}</span>
                    <input className="input mt-1 w-full" required maxLength={64} value={number} autoComplete="off"
                      placeholder={t("eotinish.numberHint")} onChange={(e) => setNumber(e.target.value)} />
                  </label>
                  <label className="block text-sm">
                    <span className="text-xs text-muted">{t("eotinish.date")}</span>
                    <input type="date" className="input mt-1 w-full" required max={today()} value={date}
                      onChange={(e) => setDate(e.target.value)} />
                  </label>
                  {proof && <p className="flex items-center gap-1.5 text-xs text-muted"><Icon name="paperclip" size={14} />{t("eotinish.receiptSaved")}</p>}
                  <Button type="submit" className="min-h-11 w-full sm:w-auto" icon="check" disabled={busy || !number.trim() || !date}>
                    {t("eotinish.save")}
                  </Button>
                  <p className="text-xs text-muted">{t("eotinish.saveHint")}</p>
                </form>
              )}
            </div>
          ))}
        </ol>
      )}
      {error && <Alert tone="danger" icon="alert">{error}</Alert>}
    </section>
  );
}

/** The proof of filing once the number is entered: number, date, body, and the receipt (can be added later). */
export function EotinishFiled({ caseId, a, onCase }: { caseId: string; a: CaseAction; onCase?: (c: CaseView) => void }) {
  const t = useT();
  const { lang } = useLang();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const f = a.filed;
  if (!f) return null;
  const addReceipt = async (file: File) => {
    setBusy(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("kind", "filing_receipt");
      const up = await api<{ evidence: { id: string } }>(`/v1/cases/${caseId}/evidence`, { method: "POST", body: form });
      const out = await api<{ case: CaseView }>(`/v1/cases/${caseId}/actions/${a.id}/portal-filing/receipt`, {
        method: "POST", body: JSON.stringify({ evidence_id: up.evidence.id }) });
      onCase?.(out.case);
    } catch (e) { setError(errorText(e)); }
    finally { setBusy(false); }
  };
  return (
    <section className="space-y-2 rounded-2xl border border-line bg-surface p-4" aria-labelledby={`eot-filed-${a.id}`}>
      <h4 id={`eot-filed-${a.id}`} className="flex items-center gap-2 font-semibold text-ink"><Icon name="checkCircle" size={18} className="text-brand" />{t("eotinish.filedTitle")}</h4>
      <dl className="grid gap-2 text-sm sm:grid-cols-2">
        <div><dt className="text-xs text-muted">{t("eotinish.number")}</dt><dd className="font-semibold tabular-nums">{f.number}</dd></div>
        <div><dt className="text-xs text-muted">{t("eotinish.date")}</dt><dd className="tabular-nums">{new Date(`${f.filed_at}T12:00:00`).toLocaleDateString(lang === "ar" ? "ar" : "ru-RU")}</dd></div>
        <div className="sm:col-span-2"><dt className="text-xs text-muted">{t("eotinish.recipient")}</dt><dd className="break-words">{f.body}</dd></div>
      </dl>
      {f.receipt_evidence_id
        ? <p className="flex items-center gap-1.5 text-xs text-muted"><Icon name="paperclip" size={14} />{t("eotinish.receiptSaved")}</p>
        : (
          <div className="flex flex-wrap items-center gap-2">
            <FilePicker disabled={busy} onFile={addReceipt} attachLabel={t("eotinish.receiptAttach")} />
          </div>
        )}
      <p className="text-xs text-muted">{t("eotinish.filedHint")}</p>
      {error && <Alert tone="danger" icon="alert">{error}</Alert>}
    </section>
  );
}
