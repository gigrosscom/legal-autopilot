"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { CodeForm, useAuthError } from "@/components/CodeForm";
import { Invite } from "@/components/Invite";
import { PushToggle } from "@/components/PushToggle";
import { ProviderSignIn } from "@/components/ProviderSignIn";
import { Alert, Badge, Button, Icon, type IconName } from "@/components/ui";
import { api, applySignIn, errorText, type AuthMethods, type Me, type SignedIn } from "@/lib/api";
import { useLang, useT } from "@/lib/i18n";
import { signForAuth } from "@/lib/ncalayer";

type Method = "email" | "phone" | "ecp" | "egov";
const METHODS: { id: Method; icon: IconName }[] = [
  { id: "email", icon: "mail" },
  { id: "phone", icon: "phone" },
  { id: "ecp", icon: "key" },
  { id: "egov", icon: "smartphone" },
];

export default function AccountPage() {
  const t = useT();
  const [me, setMe] = useState<Me | null>(null);
  const [methods, setMethods] = useState<AuthMethods | null>(null);
  const [open, setOpen] = useState<Method | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sheet, setSheet] = useState(false);  // «Войти или зарегистрироваться»: Google · Apple · e-mail

  useEffect(() => {
    api<Me>("/v1/me").then(setMe).catch((e) => setError(errorText(e)));
    api<AuthMethods>("/v1/auth/methods").then(setMethods).catch(() => setMethods({ email: false, phone: false, ecp: false, egov: false }));
  }, []);

  const signedIn = (r: SignedIn) => {
    setMe(applySignIn(r));
    setOpen(null); setSheet(false);
    setDone(t("account.done"));
    const next = new URLSearchParams(window.location.search).get("next");
    if (next && next.startsWith("/") && !next.startsWith("//")) setTimeout(() => { window.location.href = next; }, 800);
  };

  useEffect(() => {  // ?method=ecp: arrive with the ЭЦП form already open (lawyer onboarding)
    const m = new URLSearchParams(window.location.search).get("method");
    if (m === "ecp" || m === "egov") setOpen(m);
    if (new URLSearchParams(window.location.search).get("signin") === "1") setSheet(true);
  }, []);
  const signedInAlready = !!me && me.identities.length > 0;

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div className="space-y-2">
        <h1 className="text-[30px] font-semibold leading-tight">{t("account.title")}</h1>
        {!signedInAlready && <p className="text-[17px] text-muted">{t("account.lead")}</p>}
      </div>

      {error && <Alert tone="danger" role="alert">{error}</Alert>}
      {done && <Alert tone="info" role="status">{done}</Alert>}

      {me && me.bonus_documents > 0 && (
        <Alert tone="info" icon="checkCircle" role="status">{t("account.bonus", { n: me.bonus_documents })}</Alert>
      )}

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

      {me && !signedInAlready && (
        <Button size="lg" className="min-h-14 w-full text-[18px]" icon="login" onClick={() => { setSheet(true); setDone(null); }}>
          {t("account.signInOrUp")}
        </Button>
      )}
      {sheet && methods && me && !signedInAlready && (
        <SignInSheet methods={methods} onClose={() => setSheet(false)} onDone={signedIn}
          onOther={() => { setSheet(false); setOpen("ecp"); document.getElementById("ways")?.scrollIntoView({ behavior: "smooth" }); }} />
      )}

      {(signedInAlready || open) && (
      <section aria-labelledby="ways" className="space-y-3">
        <h2 id="ways" className="text-lg font-semibold">{t(signedInAlready ? "account.moreWaysTitle" : "account.waysTitle")}</h2>
        {/* only the ways that work on the server: a switched-off one is not shown at all (no «скоро») */}
        {METHODS.filter((m) => methods?.[m.id]).map((m) => {
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
      )}

      <PushToggle />

      {signedInAlready && <ReportsToggle me={me} onChange={setMe} />}

      {signedInAlready && <p className="text-xs text-muted">{t("account.privacy")}</p>}

      <Invite />
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
              {/* a new window: from the installed app the link leaves for the browser, which hands it to eGov Mobile;
                  the app keeps waiting for the signature here */}
              <a className="btn-ghost" href={start.links.egov_mobile} target="_blank" rel="noopener noreferrer">eGov Mobile</a>
              <a className="btn-ghost" href={start.links.egov_business} target="_blank" rel="noopener noreferrer">eGov Business</a>
            </div>
            <p className="flex items-center gap-2 text-muted" role="status"><Icon name="spinner" size={16} />{t("account.egov.waiting")}</p>
          </div>
        </div>
      )}
      {error && <p role="alert" className="text-danger">{error}</p>}
    </div>
  );
}

/** «Войти или зарегистрироваться»: one sheet with the three ways — Google, Apple (when set up) and e-mail with a code.
 *  Signing in and signing up are the same step: a new person gets an account, a known one gets theirs back. */
function SignInSheet({ methods, onClose, onDone, onOther }: {
  methods: AuthMethods; onClose: () => void; onDone: (r: SignedIn) => void; onOther: () => void;
}) {
  const t = useT();
  const [email, setEmail] = useState(false);
  const panel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    panel.current?.focus();
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", esc);
    return () => document.removeEventListener("keydown", esc);
  }, [onClose]);
  const other = methods.ecp || methods.egov || methods.phone;
  // drawn over the whole app (tab bar included), not inside the page
  return createPortal(
    <div className="fixed inset-0 z-[70] flex items-end justify-center sm:items-center" role="dialog" aria-modal="true" aria-labelledby="signin-title">
      <button type="button" aria-label={t("app.close")} onClick={onClose} className="absolute inset-0 bg-black/40" />
      <div ref={panel} tabIndex={-1}
        className="relative w-full max-w-md space-y-4 rounded-t-3xl bg-surface p-5 pb-[max(1.25rem,env(safe-area-inset-bottom))] outline-none sm:rounded-3xl">
        <div className="flex items-start justify-between gap-3">
          <div className="space-y-1">
            <h2 id="signin-title" className="text-[22px] font-semibold">{t("account.signInOrUp")}</h2>
            <p className="text-[15px] text-muted">{t("account.signInLead")}</p>
          </div>
          <button type="button" onClick={onClose} aria-label={t("app.close")}
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-sand hover:bg-sand-deep"><Icon name="x" size={20} /></button>
        </div>
        <ProviderSignIn google={!!methods.google} apple={!!methods.apple} onDone={onDone} />
        {methods.email && (email ? <CodeForm kind="email" onDone={onDone} wide /> : (
          <button type="button" onClick={() => setEmail(true)}
            className="flex min-h-12 w-full items-center justify-center gap-2 rounded-full border border-line bg-surface px-4 text-[17px] font-semibold text-ink hover:bg-sand">
            <Icon name="mail" size={20} />{t("account.withEmail")}
          </button>
        ))}
        {other && (
          <button type="button" onClick={onOther} className="mx-auto block min-h-10 text-[15px] text-muted underline-offset-4 hover:text-ink hover:underline">
            {t("account.otherWays")}
          </button>
        )}
      </div>
    </div>,
    document.body,
  );
}
