"use client";

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { InstallButton } from "@/components/InstallApp";
import { ThemePicker } from "@/components/ThemePicker";
import { Icon, type IconName } from "@/components/ui";
import { adminApi, ApiError, errorText } from "@/lib/api";
import type { Bundle } from "@/lib/team";
import { Deals } from "./Deals";
import { Decisions } from "./Decisions";
import { Goals } from "./Goals";
import { pendingOf, type Metrics } from "./model";
import { Operations } from "./Operations";
import { Questions } from "./Questions";
import { FileView, Reports } from "./Reports";
import { Summary } from "./Summary";
import { Tasks } from "./Tasks";
import { TeamTab } from "./TeamTab";
import { CentreContext, type Centre, type TabKey } from "./ui";

// Same key as /admin: signing in once on a device opens both.
const TOKEN_KEY = "konsilier.admin";
const INSTALL_KEY = "konsilier.opsInstalled";

const TABS: { key: TabKey; label: string; icon: IconName }[] = [
  { key: "home", label: "Сводка", icon: "home" },
  { key: "deals", label: "Сделки", icon: "briefcase" },
  { key: "questions", label: "Вопросы", icon: "chat" },
  { key: "goals", label: "Цели и курс", icon: "map" },
  { key: "team", label: "Команда", icon: "users" },
  { key: "tasks", label: "Задачи", icon: "check" },
  { key: "decisions", label: "Решения", icon: "scroll" },
  { key: "reports", label: "Отчёты", icon: "document" },
  { key: "ops", label: "Операции", icon: "briefcase" },
];
const PHONE_TABS: TabKey[] = ["home", "deals", "tasks", "decisions"];
const isTab = (v: string | null): v is TabKey => TABS.some((t) => t.key === v);

function readToken(): string | null {
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}
function writeToken(v: string | null) {
  try { if (v) localStorage.setItem(TOKEN_KEY, v); else localStorage.removeItem(TOKEN_KEY); } catch {}
}

/** «Konsiliér Ops»: the owner's command centre, one app for the phone and the computer. */
export function CommandCentre() {
  const [token, setToken] = useState<string | null | undefined>(undefined);
  useEffect(() => { setToken(readToken()); }, []);
  const signOut = useCallback(() => { writeToken(null); setToken(null); }, []);
  if (token === undefined) return null;
  if (!token) return <SignIn onDone={(t) => { writeToken(t); setToken(t); }} />;
  return <Centre token={token} onSignOut={signOut} />;
}

function SignIn({ onDone }: { onDone: (token: string) => void }) {
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      await adminApi("/v1/admin/metrics?weeks=1", value.trim());
      onDone(value.trim());
    } catch (err) {
      setError(err instanceof ApiError && err.status === 403 ? "Ключ не подошёл." : errorText(err));
    } finally { setBusy(false); }
  }
  return (
    <main className="flex min-h-screen items-center justify-center bg-surface px-4 py-10">
      <form onSubmit={submit} className="w-full max-w-sm space-y-5 text-center">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/icons/ops/icon-192.png" alt="" width={72} height={72} className="mx-auto rounded-[18px]" />
        <div>
          <h1 className="text-[28px] font-semibold">Konsiliér Ops</h1>
          <p className="mt-2 text-[16px] text-muted">Командный центр владельца. Войдите ключом администратора — он задан в настройках сервера (ADMIN_TOKEN). Ключ хранится только на этом устройстве.</p>
        </div>
        <input type="password" autoComplete="current-password" value={value} onChange={(e) => setValue(e.target.value)}
          placeholder="Ключ администратора" aria-label="Ключ администратора"
          className="min-h-12 w-full rounded-full bg-sand px-5 text-[17px] outline-none placeholder:text-muted focus:ring-2 focus:ring-accent" />
        {error && <p role="alert" className="text-danger">{error}</p>}
        <button type="submit" disabled={busy || !value.trim()}
          className="min-h-12 w-full rounded-full bg-action text-[17px] font-semibold text-white hover:bg-action-hover disabled:opacity-50">
          {busy ? "Проверяем…" : "Войти"}
        </button>
        <InstallButton storeKey={INSTALL_KEY} icon="smartphone" label="Установить на рабочий стол"
          className="flex min-h-12 w-full items-center justify-center gap-2 rounded-full border border-line bg-surface text-[17px] font-semibold text-action hover:bg-sand" />
      </form>
    </main>
  );
}

function Centre({ token, onSignOut }: { token: string; onSignOut: () => void }) {
  const [tab, setTab] = useState<TabKey>("home");
  const [file, setFile] = useState<string | null>(null);
  const [more, setMore] = useState(false);
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [metricsError, setMetricsError] = useState<string | null>(null);
  const [bundle, setBundle] = useState<Bundle | null>(null);
  const [teamError, setTeamError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // the tab lives in the address (?tab=team): the app's shortcuts and a notification can open it
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    const t = q.get("tab");
    if (isTab(t)) setTab(t);
    const f = q.get("file");
    if (f) setFile(f);
    const onPop = () => {
      const p = new URLSearchParams(window.location.search);
      const pt = p.get("tab");
      setTab(isTab(pt) ? pt : "home");
      setFile(p.get("file"));
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);
  const push = (t: TabKey, f: string | null) => {
    const q = new URLSearchParams();
    if (t !== "home") q.set("tab", t);
    if (f) q.set("file", f);
    const url = `/ops${q.size ? `?${q}` : ""}`;
    window.history.pushState(null, "", url);
  };
  const go = useCallback((t: TabKey) => { setTab(t); setFile(null); setMore(false); push(t, null); window.scrollTo(0, 0); }, []);
  const openFile = useCallback((p: string) => { setFile(p); push(tab, p); }, [tab]);
  const closeFile = useCallback(() => {
    if (new URLSearchParams(window.location.search).get("file")) window.history.back(); else setFile(null);
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    const denied = (e: unknown) => e instanceof ApiError && e.status === 403;
    await Promise.all([
      adminApi<Metrics>("/v1/admin/metrics?weeks=12", token)
        .then((m) => { setMetrics(m); setMetricsError(null); })
        .catch((e) => { if (denied(e)) onSignOut(); else setMetricsError(errorText(e)); }),
      adminApi<Bundle>("/v1/admin/team/bundle", token)
        .then((b) => { setBundle(b); setTeamError(null); })
        .catch((e) => {
          if (denied(e)) onSignOut();
          else setTeamError(e instanceof ApiError && e.code === "team_unavailable" ? "unavailable" : errorText(e));
        }),
    ]);
    setLoading(false);
  }, [token, onSignOut]);
  useEffect(() => { load(); }, [load]);

  const pending = useMemo(() => pendingOf(bundle).length, [bundle]);
  const ctx: Centre = { token, metrics, metricsError, bundle, teamError, go, openFile, reload: load };
  const current = TABS.find((t) => t.key === tab)!;
  const body: Record<TabKey, ReactNode> = {
    home: <Summary />, deals: <Deals />, questions: <Questions />, goals: <Goals />, team: <TeamTab />, tasks: <Tasks />, decisions: <Decisions />,
    reports: <Reports />, ops: <Operations />,
  };
  const badge = (k: TabKey) => (k === "decisions" && pending > 0 ? pending : null);

  return (
    <CentreContext.Provider value={ctx}>
      {/* computer: sidebar */}
      <aside className="fixed inset-y-0 start-0 z-30 hidden w-64 flex-col border-e border-line bg-sand px-4 py-6 lg:flex">
        <div className="flex items-center gap-3 px-2">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/icons/ops/icon-192.png" alt="" width={36} height={36} className="rounded-[10px]" />
          <div className="leading-tight">
            <p className="text-[17px] font-semibold">Konsiliér</p>
            <p className="text-[15px] text-muted">Команда</p>
          </div>
        </div>
        <nav aria-label="Разделы" className="mt-8">
          <ul className="space-y-1">
            {TABS.map((t) => (
              <li key={t.key}>
                <button type="button" onClick={() => go(t.key)} aria-current={tab === t.key ? "page" : undefined}
                  className={`flex min-h-11 w-full items-center gap-3 rounded-xl px-3 text-[16px] ${tab === t.key ? "bg-sand-deep font-semibold text-ink" : "text-ink-soft hover:bg-sand-deep"}`}>
                  <Icon name={t.icon} size={20} className={tab === t.key ? "text-action" : "text-muted"} />
                  <span className="flex-1 text-start">{t.label}</span>
                  {badge(t.key) != null && <span className="rounded-full bg-action px-2 text-[13px] font-semibold text-white tabular-nums">{badge(t.key)}</span>}
                </button>
              </li>
            ))}
          </ul>
        </nav>
        <div className="mt-auto space-y-2 border-t border-line pt-4">
          <InstallButton storeKey={INSTALL_KEY} icon="smartphone" label="Установить на рабочий стол"
            className="flex min-h-11 w-full items-center justify-center gap-2 rounded-full bg-action px-3 text-[15px] font-semibold text-white hover:bg-action-hover" />
          <button type="button" onClick={load} disabled={loading}
            className="flex min-h-10 w-full items-center gap-3 rounded-xl px-3 text-[15px] text-ink-soft hover:bg-sand-deep disabled:opacity-60">
            <Icon name={loading ? "spinner" : "clock"} size={18} className={`text-muted ${loading ? "animate-spin" : ""}`} />Обновить данные
          </button>
          <a href="/" className="flex min-h-10 items-center gap-3 rounded-xl px-3 text-[15px] text-ink-soft hover:bg-sand-deep">
            <Icon name="external" size={18} className="text-muted" />Сайт konsilier.com
          </a>
          <div className="space-y-2 px-1 pt-2">
            <p className="text-[13px] font-semibold text-muted">Оформление</p>
            <ThemePicker compact />
          </div>
          <button type="button" onClick={onSignOut} className="mt-2 flex min-h-10 w-full items-center gap-3 rounded-xl border-t border-line px-3 pt-1 text-[15px] font-medium text-danger hover:bg-sand-deep">
            <Icon name="login" size={18} className="rotate-180" />Выйти
          </button>
        </div>
      </aside>

      {/* phone: top bar */}
      <header className="sticky top-0 z-20 border-b border-ink/[0.08] bg-bar/92 pt-[env(safe-area-inset-top)] backdrop-blur-[20px] lg:hidden">
        <div className="flex h-14 items-center justify-between gap-2 px-4">
          <div className="flex min-w-0 items-center gap-2.5">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/icons/ops/icon-192.png" alt="" width={30} height={30} className="rounded-[8px]" />
            <p className="truncate text-[17px] font-semibold">Konsiliér Ops</p>
          </div>
          <div className="flex items-center gap-1">
            <InstallButton storeKey={INSTALL_KEY} label="Установить"
              className="min-h-9 rounded-full bg-action px-3.5 text-[15px] font-semibold text-white" />
            <button type="button" onClick={load} aria-label="Обновить данные" disabled={loading}
              className="flex h-10 w-10 items-center justify-center rounded-full text-ink hover:bg-sand">
              <Icon name={loading ? "spinner" : "clock"} size={20} className={loading ? "animate-spin" : ""} />
            </button>
          </div>
        </div>
      </header>

      <main id="main" className="mx-auto w-full max-w-6xl px-4 pt-5 pb-[calc(6rem+env(safe-area-inset-bottom))] lg:ps-72 lg:pe-10 lg:pt-10 lg:pb-16">
        <div key={tab} className="lg:max-w-none">{body[tab]}</div>
      </main>

      {/* phone: tab bar */}
      <nav aria-label="Разделы" className="fixed inset-x-0 bottom-0 z-30 border-t border-line bg-surface pb-[env(safe-area-inset-bottom)] lg:hidden">
        <ul className="mx-auto grid max-w-lg grid-cols-5">
          {[...PHONE_TABS.map((k) => TABS.find((t) => t.key === k)!), { key: "more" as const, label: "Ещё", icon: "menu" as IconName }].map((t) => {
            const on = t.key === "more" ? !PHONE_TABS.includes(tab) : tab === t.key;
            const b = t.key === "more" ? null : badge(t.key);
            return (
              <li key={t.key}>
                <button type="button" aria-current={on ? "page" : undefined}
                  onClick={() => (t.key === "more" ? setMore(true) : go(t.key))}
                  className={`relative flex h-16 w-full flex-col items-center justify-center gap-1 text-[12px] ${on ? "font-semibold text-action" : "text-muted"}`}>
                  <Icon name={t.icon} size={24} strokeWidth={on ? 2.1 : 1.7} />
                  <span className="max-w-full truncate px-0.5">{t.key === "more" && on ? current.label : t.label}</span>
                  {b != null && <span className="absolute top-1.5 left-[calc(50%+6px)] min-w-5 rounded-full bg-action px-1.5 text-[11px] leading-5 font-semibold text-white tabular-nums">{b}</span>}
                </button>
              </li>
            );
          })}
        </ul>
      </nav>

      {more && <MoreSheet tab={tab} go={go} onClose={() => setMore(false)} onSignOut={onSignOut} />}
      {file && <FileView path={file} onClose={closeFile} />}
    </CentreContext.Provider>
  );
}

function MoreSheet({ tab, go, onClose, onSignOut }: { tab: TabKey; go: (t: TabKey) => void; onClose: () => void; onSignOut: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);
  const rest = TABS.filter((t) => !PHONE_TABS.includes(t.key));
  return (
    <div className="fixed inset-0 z-40 lg:hidden" onClick={onClose}>
      <div className="absolute inset-0 bg-black/30" aria-hidden="true" />
      <div role="dialog" aria-modal="true" aria-label="Ещё" onClick={(e) => e.stopPropagation()}
        className="absolute inset-x-0 bottom-0 rounded-t-3xl bg-surface px-4 pt-3 pb-[calc(1rem+env(safe-area-inset-bottom))] shadow-[0_-8px_30px_rgb(0_0_0/0.15)]">
        <div className="mx-auto mb-3 h-1.5 w-10 rounded-full bg-line" aria-hidden="true" />
        <ul className="space-y-1">
          {rest.map((t) => (
            <li key={t.key}>
              <button type="button" onClick={() => go(t.key)} aria-current={tab === t.key ? "page" : undefined}
                className={`flex min-h-14 w-full items-center gap-4 rounded-2xl px-3 text-[17px] ${tab === t.key ? "bg-sand font-semibold" : "hover:bg-sand"}`}>
                <span className="flex h-10 w-10 items-center justify-center rounded-full bg-brand-50 text-action"><Icon name={t.icon} size={20} /></span>{t.label}
              </button>
            </li>
          ))}
        </ul>
        <div className="mt-3 space-y-1 border-t border-line pt-3">
          <InstallButton storeKey={INSTALL_KEY} icon="smartphone" label="Установить на телефон"
            className="flex min-h-12 w-full items-center justify-center gap-2 rounded-full bg-action text-[17px] font-semibold text-white" />
          <a href="/" className="flex min-h-12 items-center gap-4 rounded-2xl px-3 text-[16px] text-ink-soft hover:bg-sand">
            <Icon name="external" size={20} className="text-muted" />Сайт konsilier.com
          </a>
          <div className="space-y-2 px-1 py-2">
            <p className="text-[14px] font-semibold text-muted">Оформление</p>
            <ThemePicker compact />
          </div>
          <button type="button" onClick={onSignOut} className="flex min-h-12 w-full items-center gap-4 rounded-2xl border-t border-line px-3 text-[16px] font-medium text-danger hover:bg-sand">
            <Icon name="login" size={20} className="rotate-180" />Выйти
          </button>
        </div>
      </div>
    </div>
  );
}
