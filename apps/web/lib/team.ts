// Reading the AI team's Markdown files (branch claude/ai-team, folder team/) for the command centre (/ops).
// Everything shown comes from these files or from /v1/admin/metrics: nothing is guessed. A table or a section that
// is not there yields an empty list, and the screen says «нет данных».

export type Table = { heading: string; headers: string[]; rows: string[][] };
export type Section = { heading: string; level: number; body: string };
export type Bullet = { text: string; children: string[] };

export type Bundle = {
  source: "dir" | "github";
  repo: string | null;
  ref: string | null;
  files: { path: string; size: number }[];
  reports: { name: string; path: string }[];
  texts: Record<string, string | null>;
};

const SEP = /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/;

export function splitRow(line: string): string[] {
  let s = line.trim();
  if (s.startsWith("|")) s = s.slice(1);
  if (s.endsWith("|")) s = s.slice(0, -1);
  // a pipe inside `code` is not a column border
  const cells: string[] = [];
  let cur = "", code = false;
  for (const ch of s) {
    if (ch === "`") code = !code;
    if (ch === "|" && !code) { cells.push(cur.trim()); cur = ""; } else cur += ch;
  }
  cells.push(cur.trim());
  return cells;
}

/** Every Markdown table with the heading it sits under. */
export function tables(md: string | null | undefined): Table[] {
  if (!md) return [];
  const lines = md.split("\n");
  const out: Table[] = [];
  let heading = "";
  for (let i = 0; i < lines.length; i++) {
    const h = lines[i].match(/^#{1,6}\s+(.*)$/);
    if (h) { heading = plain(h[1]); continue; }
    if (lines[i].trim().startsWith("|") && i + 1 < lines.length && SEP.test(lines[i + 1])) {
      const headers = splitRow(lines[i]).map(plain);
      const rows: string[][] = [];
      i += 2;
      while (i < lines.length && lines[i].trim().startsWith("|")) { rows.push(splitRow(lines[i])); i++; }
      i--;
      out.push({ heading, headers, rows });
    }
  }
  return out;
}

/** The first table that has a column whose header matches `col`. */
export function tableWith(md: string | null | undefined, col: RegExp): Table | null {
  return tables(md).find((t) => t.headers.some((h) => col.test(h))) ?? null;
}

/** Column index by header pattern (-1 when absent). */
export const colOf = (t: Table, re: RegExp) => t.headers.findIndex((h) => re.test(h));
export const cell = (row: string[], i: number) => (i >= 0 ? row[i] ?? "" : "");

/** Sections by heading (any level); the body runs to the next heading of the same or a higher level. */
export function sections(md: string | null | undefined): Section[] {
  if (!md) return [];
  const lines = md.split("\n");
  const heads: { i: number; level: number; heading: string }[] = [];
  lines.forEach((l, i) => {
    const m = l.match(/^(#{1,6})\s+(.*)$/);
    if (m) heads.push({ i, level: m[1].length, heading: plain(m[2]) });
  });
  return heads.map((h, k) => {
    let end = lines.length;
    for (let j = k + 1; j < heads.length; j++) if (heads[j].level <= h.level) { end = heads[j].i; break; }
    return { heading: h.heading, level: h.level, body: lines.slice(h.i + 1, end).join("\n").trim() };
  });
}

export const section = (md: string | null | undefined, re: RegExp) => sections(md).find((s) => re.test(s.heading)) ?? null;

/** Top-level list items with their nested lines. */
export function bullets(md: string | null | undefined): Bullet[] {
  if (!md) return [];
  const out: Bullet[] = [];
  for (const raw of md.split("\n")) {
    const top = raw.match(/^[-*]\s+(.*)$/) ?? raw.match(/^\d+[.)]\s+(.*)$/);
    const sub = raw.match(/^\s{2,}(?:[-*]|\d+[.)])\s+(.*)$/);
    if (top) out.push({ text: top[1].trim(), children: [] });
    else if (sub && out.length) out[out.length - 1].children.push(sub[1].trim());
    else if (/^\s{2,}\S/.test(raw) && out.length) {
      const b = out[out.length - 1];
      if (b.children.length) b.children[b.children.length - 1] += ` ${raw.trim()}`; else b.text += ` ${raw.trim()}`;
    }
  }
  return out;
}

/** Text without Markdown marks: **bold**, `code`, [text](url) → text. */
export function plain(s: string): string {
  return s.replace(/\[([^\]]+)\]\([^)]*\)/g, "$1").replace(/\*\*([^*]+)\*\*/g, "$1").replace(/`([^`]+)`/g, "$1")
    .replace(/(^|\s)\*([^*]+)\*/g, "$1$2").trim();
}

export function firstLink(s: string): { text: string; url: string } | null {
  const m = s.match(/\[([^\]]+)\]\(([^)\s]+)\)/);
  return m ? { text: m[1], url: m[2] } : null;
}

/** «100 000» → 100000; null when the cell holds no number. */
export function number(s: string): number | null {
  const m = plain(s).replace(/[\s  ]/g, "").match(/\d+(?:[.,]\d+)?/);
  return m ? Number(m[0].replace(",", ".")) : null;
}

/** «30.09.2026» → Date (local midnight), null otherwise. */
export function ruDate(s: string): Date | null {
  const m = s.match(/(\d{2})\.(\d{2})\.(\d{4})/);
  return m ? new Date(Number(m[3]), Number(m[2]) - 1, Number(m[1])) : null;
}

export const isEmpty = (s: string) => !plain(s) || /^[—–-]+$/.test(plain(s));

/** Backlog status → board column. */
export type TaskState = "waiting" | "doing" | "new" | "done" | "other";
export function taskState(status: string): TaskState {
  const s = plain(status).toLowerCase();
  if (/ждёт владельца|ждет владельца|ждёт|ждет/.test(s) && !/^готово: в проде/.test(s)) return "waiting";
  if (s.startsWith("готово")) return "done";
  if (s.startsWith("в работе")) return "doing";
  if (s.startsWith("новая")) return "new";
  return "other";
}

/** «2026-09-30-am.md» → «30.09.2026 · утро». */
export function reportTitle(name: string): string {
  const m = name.match(/^(\d{4})-(\d{2})-(\d{2})(?:-(am|pm))?/);
  if (!m) return name.replace(/\.md$/, "");
  return `${m[3]}.${m[2]}.${m[1]}${m[4] ? ` · ${m[4] === "am" ? "утро" : "вечер"}` : ""}`;
}

/** Simple CSV (quoted fields allowed) → rows. */
export function csv(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [], cur = "", q = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (q) {
      if (ch === '"' && text[i + 1] === '"') { cur += '"'; i++; } else if (ch === '"') q = false; else cur += ch;
    } else if (ch === '"') q = true;
    else if (ch === ",") { row.push(cur); cur = ""; }
    else if (ch === "\n" || ch === "\r") {
      if (ch === "\r" && text[i + 1] === "\n") i++;
      row.push(cur); cur = "";
      if (row.some((c) => c.trim())) rows.push(row);
      row = [];
    } else cur += ch;
  }
  row.push(cur);
  if (row.some((c) => c.trim())) rows.push(row);
  return rows;
}
