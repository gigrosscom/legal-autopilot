"use client";

import { useEffect, useMemo, useState } from "react";
import { Markdown } from "@/components/Markdown";
import { Icon } from "@/components/ui";
import { adminApi, ApiError, errorText } from "@/lib/api";
import { csv, reportTitle } from "@/lib/team";
import { H2, Loading, PageTitle, RowLink, TeamUnavailable, useCentre } from "./ui";

/** Reports (newest first) and every other file of team/: tap to read. New files appear without code changes. */
export function Reports() {
  const c = useCentre();
  const [q, setQ] = useState("");
  const b = c.bundle;
  const groups = useMemo(() => {
    const out = new Map<string, { path: string; name: string }[]>();
    for (const f of b?.files ?? []) {
      if (f.path.startsWith("team/reports/")) continue;
      const rest = f.path.slice("team/".length);
      const i = rest.lastIndexOf("/");
      const folder = i < 0 ? "" : rest.slice(0, i);
      out.set(folder, [...(out.get(folder) ?? []), { path: f.path, name: i < 0 ? rest : rest.slice(i + 1) }]);
    }
    return [...out.entries()].sort(([a], [z]) => a.localeCompare(z));
  }, [b]);
  if (c.teamError) return <div className="space-y-6"><PageTitle>Отчёты</PageTitle><TeamUnavailable /></div>;
  if (!b) return <div className="space-y-6"><PageTitle>Отчёты</PageTitle><Loading /></div>;
  const needle = q.trim().toLowerCase();

  return (
    <div className="space-y-8">
      <PageTitle sub="Утренние и вечерние отчёты менеджера проекта (reports/) и все файлы команды.">Отчёты</PageTitle>
      <section className="space-y-3">
        <H2 count={b.reports.length}>Отчёты</H2>
        {b.reports.length === 0 && <p className="text-muted">Отчётов пока нет.</p>}
        <ul className="space-y-2">
          {b.reports.map((r, i) => (
            <li key={r.path}>
              <RowLink icon="document" title={reportTitle(r.name)} sub={i === 0 ? "последний" : r.name} onClick={() => c.openFile(r.path)} />
            </li>
          ))}
        </ul>
      </section>
      <section className="space-y-3">
        <H2 count={b.files.length - b.reports.length}>Все файлы команды</H2>
        <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Поиск по названию файла"
          className="min-h-12 w-full rounded-full bg-sand px-5 text-[17px] outline-none placeholder:text-muted focus:ring-2 focus:ring-accent" />
        {groups.map(([folder, files]) => {
          const list = files.filter((f) => !needle || f.path.toLowerCase().includes(needle));
          if (!list.length) return null;
          return (
            <div key={folder || "root"} className="space-y-1">
              <p className="px-1 text-[14px] font-semibold text-muted">{folder ? `${folder}/` : "team/"}</p>
              <ul className="divide-y divide-line/70 overflow-hidden rounded-2xl bg-sand">
                {list.map((f) => (
                  <li key={f.path}>
                    <button type="button" onClick={() => c.openFile(f.path)}
                      className="flex min-h-12 w-full items-center gap-3 px-4 text-start text-[16px] hover:bg-sand-deep">
                      <Icon name={f.name.endsWith(".csv") ? "chart" : "document"} size={18} className="shrink-0 text-muted" />
                      <span className="min-w-0 flex-1 truncate">{f.name}</span>
                      <Icon name="arrowRight" size={16} className="shrink-0 text-muted" />
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          );
        })}
      </section>
    </div>
  );
}

/** One team file, full screen on a phone, a wide panel on a computer. Markdown is rendered as React elements. */
export function FileView({ path, onClose }: { path: string; onClose: () => void }) {
  const c = useCentre();
  const cached = c.bundle?.texts[path];
  const [text, setText] = useState<string | null>(cached ?? null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (cached) { setText(cached); return; }
    setText(null); setError(null);
    adminApi<{ text: string }>(`/v1/admin/team/file?path=${encodeURIComponent(path)}`, c.token)
      .then((r) => setText(r.text))
      .catch((e) => setError(e instanceof ApiError && e.status === 404 ? "Такого файла нет в ветке команды."
        : e instanceof ApiError && e.code === "team_unavailable" ? "Файлы команды сейчас недоступны." : errorText(e)));
  }, [path, cached, c.token]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);
  const base = path.slice(0, path.lastIndexOf("/") + 1);
  const name = path.slice(base.length);
  const title = path.startsWith("team/reports/") ? `Отчёт ${reportTitle(name)}` : name;
  const gh = c.bundle?.repo && c.bundle.ref ? `https://github.com/${c.bundle.repo}/blob/${c.bundle.ref}/${path}` : null;

  return (
    <div role="dialog" aria-modal="true" aria-label={title} className="fixed inset-0 z-50 flex flex-col bg-surface lg:ps-64">
      <header className="sticky top-0 z-10 border-b border-line bg-surface/95 pt-[env(safe-area-inset-top)] backdrop-blur">
        <div className="mx-auto flex h-14 max-w-4xl items-center gap-2 px-2 lg:px-6">
          <button type="button" onClick={onClose} aria-label="Назад"
            className="flex h-11 min-w-11 items-center justify-center gap-1 rounded-full px-2 text-[17px] text-brand hover:bg-sand">
            <Icon name="arrowRight" size={20} className="rotate-180" /><span className="max-sm:sr-only">Назад</span>
          </button>
          <p className="min-w-0 flex-1 truncate text-center text-[17px] font-semibold lg:text-start">{title}</p>
          {gh ? (
            <a href={gh} target="_blank" rel="noopener noreferrer"
              aria-label="Открыть на GitHub" className="flex h-11 w-11 items-center justify-center rounded-full text-muted hover:bg-sand"><Icon name="external" size={20} /></a>
          ) : <span className="w-11" />}
        </div>
      </header>
      <div className="flex-1 overflow-y-auto">
        <article className="mx-auto max-w-4xl px-4 pt-5 pb-[calc(2rem+env(safe-area-inset-bottom))] text-[17px] leading-relaxed lg:px-8">
          <p className="mb-4 text-[14px] text-muted break-all">{path}</p>
          {error ? <p role="alert" className="text-danger">{error}</p> : text == null ? <Loading />
            : name.endsWith(".csv") ? <CsvTable text={text} />
            : <Markdown doc text={text} base={base} onFile={c.openFile} />}
        </article>
      </div>
    </div>
  );
}

function CsvTable({ text }: { text: string }) {
  const rows = csv(text);
  if (!rows.length) return <p className="text-muted">Файл пуст.</p>;
  const [head, ...body] = rows;
  return (
    <div className="space-y-2">
      <p className="text-[15px] text-muted">Строк: {body.length}</p>
      <div className="overflow-x-auto">
        <table className="min-w-full border-collapse text-left text-[14px]">
          <thead><tr>{head.map((h, i) => <th key={i} className="border-b border-line px-2 py-2 font-semibold whitespace-nowrap">{h}</th>)}</tr></thead>
          <tbody>{body.map((r, i) => (
            <tr key={i} className="align-top">{head.map((_, j) => <td key={j} className="border-b border-line/60 px-2 py-1.5">{r[j] ?? ""}</td>)}</tr>
          ))}</tbody>
        </table>
      </div>
    </div>
  );
}
