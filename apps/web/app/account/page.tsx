"use client";

import { useEffect, useRef, useState } from "react";
import { Alert, Badge, Button, Icon, type IconName } from "@/components/ui";
import { ApiError, api, applySignIn, errorText, type AuthMethods, type Me, type SignedIn } from "@/lib/api";
import { useLang, useT } from "@/lib/i18n";
import { NcaLayerError, signForAuth } from "@/lib/ncalayer";

type Method = "email" | "phone" | "ecp" | "egov";
const METHODS: { id: Method; icon: IconName }[] = [
  { id: "email", icon: "mail" },
  { id: "phone", icon: "phone" },
  { id: "ecp", icon: "key" },
  { id: "egov", icon: "smartphone" },
];

function useAuthError() {
  const t = useT();
  return (e: unknown): string => {
    if (e instanceof ApiError && e.code) {
      const key = `account.errors.${e.code}`;
      const text = t(key);
      if (text !== key) return text;
    }
    if (e instanceof NcaLayerError) return t(`account.ecp.${e.kind}`);
    return errorText(e);
  };
}

export default function AccountPage() {
  const t = useT();
  const [me, setMe] = useState<Me | null>(null);
  const [methods, setMethods] = useState<AuthMethods | null>(null);
  const [open, setOpen] = useState<Method | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<Me>("/v1/me").then(setMe).catch((e) => setError(errorText(e)));
    api<AuthMethods>("/v1/auth/methods").then(setMethods).catch(() => setMethods({ email: false, phone: false, ecp: false, egov: false }));
  }, []);

  const signedIn = (r: SignedIn) => {
    setMe(applySignIn(r));
    setOpen(null);
    setDone(t("account.done"));
  };

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div className="space-y-2">
        <p className="eyebrow">{t("account.eyebrow")}</p>
        <h1 className="text-3xl font-bold tracking-tight">{t("account.title")}</h1>
        <p className="text-muted">{t("account.lead")}</p>
      </div>

      {error && <Alert tone="danger" role="alert">{error}</Alert>}
      {done && <Alert tone="info" role="status">{done}</Alert>}

      {me && me.identities.length > 0 && (
        <section className="card space-y-3" aria-labelledby="verified">
          <h2 id="verified" className="font-semibold">{me.display_name ?? t("account.verifiedTitle")}</h2>
          <ul className="space-y-2 text-sm">
            {me.identities.map((i) => (
              <li key={i.kind + i.display} className="flex items-center gap-2">
                <Icon name="checkCircle" size={18} className="text-brand" />
                <span className="text-muted">{t(`account.kind.${i.kind}`)}:</span>
                <span dir="ltr" className="font-medium">{i.display}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section aria-labelledby="ways" className="space-y-3">
        <h2 id="ways" className="text-lg font-semibold">{t("account.waysTitle")}</h2>
        {[...METHODS].sort((a, b) => Number(methods?.[b.id] ?? false) - Number(methods?.[a.id] ?? false)).map((m) => {
          const available = methods?.[m.id] ?? false;
          const isOpen = open === m.id;
          return (
            <div key={m.id} className={`card space-y-3 ${isOpen ? "ring-2 ring-brand/30" : ""}`}>
              <button type="button" aria-expanded={isOpen} disabled={!available}
                onClick={() => { setOpen(isOpen ? null : m.id); setDone(null); }}
                className="flex w-full items-start gap-3 text-start disabled:cursor-not-allowed">
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand">
                  <Icon name={m.icon} />
                </span>
                <span className="flex-1 space-y-1">
                  <span className="block font-semibold">{t(`account.${m.id}.title`)}</span>
                  <span className="block text-sm text-muted">{t(`account.${m.id}.hint`)}</span>
                  {methods && !available && <Badge tone="warning" icon="hourglass">{t("account.soon")}</Badge>}
                </span>
                {available && <Icon name="chevronDown" className={`mt-2.5 text-brand transition-transform ${isOpen ? "rotate-180" : ""}`} />}
              </button>
              {isOpen && m.id === "email" && <CodeForm kind="email" onDone={signedIn} />}
              {isOpen && m.id === "phone" && <CodeForm kind="phone" onDone={signedIn} />}
              {isOpen && m.id === "ecp" && <EcpForm onDone={signedIn} />}
              {isOpen && m.id === "egov" && <EgovForm onDone={signedIn} />}
            </div>
          );
        })}
      </section>

      {me && <ReportsToggle me={me} onChange={setMe} />}

      <p className="text-xs text-muted">{t("account.privacy")}</p>
    </div>
  );
}

function ReportsToggle({ me, onChange }: { me: Me; onChange: (m: Me) => void }) {
  const t = useT();
  const email = me.identities.find((i) => i.kind === "email");
  const [busy, setBusy] = useState(false);
  const toggle = async (on: boolean) => {
    setBusy(true);
    try {
      onChange(await api<Me>("/v1/me", { method: "PATCH", body: JSON.stringify({ notify_email: on }) }));
    } finally { setBusy(false); }
  };
  return (
    <section aria-labelledby="reports" className="card space-y-2 text-sm">
      <h2 id="reports" className="font-semibold">{t("reports.title")}</h2>
      <p className="text-muted">{t("reports.lead")}</p>
      {email ? (
        <label className="flex items-center gap-2">
          <input type="checkbox" className="h-5 w-5 accent-brand" checked={me.notify_email} disabled={busy}
            onChange={(e) => toggle(e.target.checked)} />
          <span>{t("reports.toggle", { email: email.display })}</span>
        </label>
      ) : <p className="text-info">{t("reports.needEmail")}</p>}
    </section>
  );
}

function CodeForm({ kind, onDone }: { kind: "email" | "phone"; onDone: (r: SignedIn) => void }) {
  const t = useT();
  const { lang } = useLang();
  const authError = useAuthError();
  const [target, setTarget] = useState("");
  const [code, setCode] = useState("");
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const send = async (e?: React.FormEvent) => {
    e?.preventDefault();
    setBusy(true); setError(null);
    try {
      await api(`/v1/auth/${kind}/start`, { method: "POST", body: JSON.stringify({ target, language: lang }) });
      setSent(true);
    } catch (err) { setError(authError(err)); } finally { setBusy(false); }
  };
  const verify = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      onDone(await api<SignedIn>(`/v1/auth/${kind}/verify`, { method: "POST", body: JSON.stringify({ target, code }) }));
    } catch (err) { setError(authError(err)); } finally { setBusy(false); }
  };

  return (
    <div className="enter space-y-3 border-t border-line pt-3">
      {!sent ? (
        <form onSubmit={send} className="space-y-3">
          <label className="block space-y-1 text-sm">
            <span className="font-medium">{t(`account.${kind}.label`)}</span>
            <input className="input" dir="ltr" required value={target} onChange={(e) => setTarget(e.target.value)}
              type={kind === "email" ? "email" : "tel"} autoComplete={kind === "email" ? "email" : "tel"}
              inputMode={kind === "email" ? "email" : "tel"} placeholder={kind === "email" ? "name@mail.kz" : "+7 701 123 45 67"} />
          </label>
          <Button disabled={busy || target.trim().length < 5} icon={busy ? "spinner" : "send"}>{t("account.sendCode")}</Button>
        </form>
      ) : (
        <form onSubmit={verify} className="space-y-3">
          <p className="text-sm text-muted">{t(`account.${kind}.sent`, { target })}</p>
          <label className="block space-y-1 text-sm">
            <span className="font-medium">{t("account.codeLabel")}</span>
            <input className="input max-w-40 text-lg tracking-[0.3em]" dir="ltr" required inputMode="numeric"
              autoComplete="one-time-code" maxLength={6} pattern="\d{6}" value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} />
          </label>
          <div className="flex flex-wrap gap-2">
            <Button disabled={busy || code.length !== 6} icon={busy ? "spinner" : "check"}>{t("account.confirm")}</Button>
            <button type="button" className="btn-ghost" onClick={() => { setSent(false); setCode(""); }}>{t("account.changeTarget")}</button>
          </div>
        </form>
      )}
      {error && <p role="alert" className="text-sm text-danger">{error}</p>}
    </div>
  );
}

function EcpForm({ onDone }: { onDone: (r: SignedIn) => void }) {
  const t = useT();
  const { lang } = useLang();
  const authError = useAuthError();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const sign = async () => {
    setBusy(true); setError(null);
    try {
      const { nonce } = await api<{ nonce: string }>("/v1/auth/ecp/challenge", { method: "POST" });
      const cms = await signForAuth(nonce, lang);
      onDone(await api<SignedIn>("/v1/auth/ecp/verify", { method: "POST", body: JSON.stringify({ nonce, cms }) }));
    } catch (err) { setError(authError(err)); } finally { setBusy(false); }
  };

  return (
    <div className="enter space-y-3 border-t border-line pt-3 text-sm">
      <ol className="list-inside list-decimal space-y-1 text-muted">
        <li>{t("account.ecp.step1")} <a className="link" href="https://pki.gov.kz/ncalayer/" target="_blank" rel="noopener noreferrer">pki.gov.kz</a></li>
        <li>{t("account.ecp.step2")}</li>
        <li>{t("account.ecp.step3")}</li>
      </ol>
      <Button onClick={sign} disabled={busy} icon={busy ? "spinner" : "key"}>{busy ? t("account.ecp.waiting") : t("account.ecp.button")}</Button>
      {error && <p role="alert" className="text-danger">{error}</p>}
    </div>
  );
}

type EgovStart = { id: string; qr: string; links: { egov_mobile: string; egov_business: string } };

function EgovForm({ onDone }: { onDone: (r: SignedIn) => void }) {
  const t = useT();
  const authError = useAuthError();
  const [start, setStart] = useState<EgovStart | null>(null);
  const [svg, setSvg] = useState<string | null>(null);
  const [status, setStatus] = useState<"pending" | "expired" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const begin = async () => {
    setError(null); setStatus(null);
    try {
      const s = await api<EgovStart>("/v1/auth/egov/start", { method: "POST" });
      setStart(s);
      const QR = (await import("qrcode")).default;
      setSvg(await QR.toString(s.qr, { type: "svg", margin: 1, errorCorrectionLevel: "M" }));
      setStatus("pending");
    } catch (err) { setError(authError(err)); }
  };

  useEffect(() => {
    if (!start || status !== "pending") return;
    timer.current = setInterval(async () => {
      try {
        const r = await api<{ status: string } & Partial<SignedIn>>(`/v1/auth/egov/status/${start.id}`);
        if (r.status === "done" && r.token && r.me) { onDone({ token: r.token, me: r.me }); setStatus(null); }
        else if (r.status === "expired" || r.status === "used") setStatus("expired");
      } catch { /* keep polling; the network may be slow */ }
    }, 2500);
    return () => { if (timer.current) clearInterval(timer.current); };
  }, [start, status, onDone]);

  return (
    <div className="enter space-y-3 border-t border-line pt-3 text-sm">
      {!start || status === "expired" ? (
        <>
          {status === "expired" && <p className="text-muted">{t("account.egov.expired")}</p>}
          <Button onClick={begin} icon="qr">{t("account.egov.button")}</Button>
        </>
      ) : (
        <div className="grid gap-4 sm:grid-cols-[180px_1fr] sm:items-center">
          {svg && <div role="img" aria-label={t("account.egov.qrAlt")} className="mx-auto w-44 rounded-xl bg-white p-2 sm:mx-0"
            dangerouslySetInnerHTML={{ __html: svg }} />}
          <div className="space-y-2">
            <p className="text-muted">{t("account.egov.scan")}</p>
            <p className="text-muted">{t("account.egov.onPhone")}</p>
            <div className="flex flex-wrap gap-2">
              <a className="btn-ghost" href={start.links.egov_mobile}>eGov Mobile</a>
              <a className="btn-ghost" href={start.links.egov_business}>eGov Business</a>
            </div>
            <p className="flex items-center gap-2 text-muted" role="status"><Icon name="spinner" size={16} />{t("account.egov.waiting")}</p>
          </div>
        </div>
      )}
      {error && <p role="alert" className="text-danger">{error}</p>}
    </div>
  );
}
