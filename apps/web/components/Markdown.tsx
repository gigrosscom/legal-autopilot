import { Fragment, type ReactNode } from "react";

type Opts = {
  /** Documents (the team's files in /ops): headings by level, tables, code blocks and quotes. */
  doc?: boolean;
  /** A relative link ([decisions.md](decisions.md)) is resolved against `base` and opened with `onFile`. */
  base?: string;
  onFile?: (path: string) => void;
};

/**
 * The little Markdown the chat model writes — paragraphs, numbered and bulleted lists, **bold**, *italic*, `code`,
 * headings and [links](https://…) — rendered as React elements (never as HTML), so a text can hold no markup of its
 * own. With `doc`, also tables, heading levels, code blocks and quotes (the team's reports and plans).
 */
export function Markdown({ text, doc = false, base = "", onFile }: { text: string } & Opts) {
  const o: Opts = { doc, base, onFile };
  const blocks: ReactNode[] = [];
  let list: { ordered: boolean; items: string[]; depth: number[]; start: number } | null = null;
  let para: string[] = [];
  const flushPara = () => {
    if (para.length) blocks.push(<p key={blocks.length}>{inline(para.join("\n"), o)}</p>);
    para = [];
  };
  const flushList = () => {
    if (!list) return;
    const { ordered, items, depth, start } = list;
    const Tag = ordered ? "ol" : "ul";
    blocks.push(
      <Tag key={blocks.length} start={ordered ? start : undefined}
        className={`space-y-1.5 ps-6 ${ordered ? "list-decimal" : "list-disc"} marker:text-muted`}>
        {items.map((it, i) => <li key={i} className={`ps-1 ${doc && depth[i] ? "ms-5 list-[circle]" : ""}`}>{inline(it, o)}</li>)}
      </Tag>);
    list = null;
  };

  const lines = text.split("\n");
  for (let i = 0; i < lines.length; i++) {
    const raw = lines[i];
    const line = raw.trimEnd();
    if (doc && line.trim().startsWith("```")) {  // code block
      flushPara(); flushList();
      const code: string[] = [];
      for (i++; i < lines.length && !lines[i].trim().startsWith("```"); i++) code.push(lines[i]);
      blocks.push(<pre key={blocks.length} className="overflow-x-auto rounded-xl bg-sand p-3 text-sm">{code.join("\n")}</pre>);
      continue;
    }
    if (doc && line.trim().startsWith("|") && i + 1 < lines.length && /^\s*\|?\s*:?-{2,}/.test(lines[i + 1])) {
      flushPara(); flushList();
      const head = cells(line);
      const rows: string[][] = [];
      for (i += 2; i < lines.length && lines[i].trim().startsWith("|"); i++) rows.push(cells(lines[i]));
      i--;
      blocks.push(
        <div key={blocks.length} className="-mx-1 overflow-x-auto px-1">
          <table className="w-full min-w-[32rem] border-collapse text-left text-[15px]">
            <thead><tr>{head.map((h, k) => <th key={k} className="border-b border-line px-2 py-2 align-bottom font-semibold">{inline(h, o)}</th>)}</tr></thead>
            <tbody>{rows.map((r, k) => (
              <tr key={k} className="align-top">{head.map((_, c) => <td key={c} className="border-b border-line/60 px-2 py-2">{inline(r[c] ?? "", o)}</td>)}</tr>
            ))}</tbody>
          </table>
        </div>);
      continue;
    }
    const ol = line.match(/^\s*(\d+)[.)]\s+(.*)$/);
    const ul = line.match(/^\s*[-*•]\s+(.*)$/);
    const h = line.match(/^(#{1,6})\s+(.*)$/);
    const quote = doc ? line.match(/^>\s?(.*)$/) : null;
    if (ol || ul) {
      flushPara();
      const ordered = !!ol;
      if (!list || list.ordered !== ordered) { flushList(); list = { ordered, items: [], depth: [], start: ol ? Number(ol[1]) : 1 }; }
      list.items.push(ol ? ol[2] : ul![1]);
      list.depth.push(/^\s{2,}/.test(raw) ? 1 : 0);
    } else if (h) {
      flushPara(); flushList();
      const level = h[1].length;
      if (!doc) blocks.push(<p key={blocks.length} className="font-semibold">{inline(h[2], o)}</p>);
      else if (level === 1) blocks.push(<h2 key={blocks.length} className="text-2xl font-semibold">{inline(h[2], o)}</h2>);
      else if (level === 2) blocks.push(<h3 key={blocks.length} className="pt-2 text-xl font-semibold">{inline(h[2], o)}</h3>);
      else blocks.push(<h4 key={blocks.length} className="pt-1 text-[17px] font-semibold">{inline(h[2], o)}</h4>);
    } else if (quote) {
      flushPara(); flushList();
      blocks.push(<blockquote key={blocks.length} className="border-s-4 border-line ps-3 text-muted">{inline(quote[1], o)}</blockquote>);
    } else if (!line.trim()) {
      flushPara(); flushList();
    } else if (list && /^\s{2,}\S/.test(raw)) {  // an indented line continues the list item
      list.items[list.items.length - 1] += ` ${line.trim()}`;
    } else {
      flushList();
      para.push(line);
    }
  }
  flushPara(); flushList();
  return <div className="space-y-3">{blocks}</div>;
}

function cells(line: string): string[] {
  let s = line.trim();
  if (s.startsWith("|")) s = s.slice(1);
  if (s.endsWith("|")) s = s.slice(0, -1);
  return s.split("|").map((c) => c.trim());
}

/** `base` folder + relative `href` → path inside the repository («team/reports/» + «../decisions.md»). */
function resolve(base: string, href: string): string {
  const parts = base.split("/").filter(Boolean);
  for (const p of href.split("#")[0].split("/")) {
    if (p === "..") parts.pop();
    else if (p && p !== ".") parts.push(p);
  }
  return parts.join("/");
}

/** **bold**, *italic*, `code` and [text](https://…) inside a line; line breaks kept. */
function inline(s: string, o: Opts = {}): ReactNode {
  const out: ReactNode[] = [];
  const re = /\*\*([^*]+)\*\*|(?<![*\w])\*([^*\n]+)\*(?![*\w])|\[([^\]]+)\]\(([^\s)]+)\)|`([^`]+)`/g;
  let last = 0, m: RegExpExecArray | null;
  while ((m = re.exec(s))) {
    if (m.index > last) out.push(s.slice(last, m.index));
    if (m[1]) out.push(<strong key={m.index} className="font-semibold">{m[1]}</strong>);
    else if (m[2]) out.push(<em key={m.index}>{m[2]}</em>);
    else if (m[5]) out.push(<code key={m.index} className="rounded bg-sand px-1 py-0.5 text-[0.9em]">{m[5]}</code>);
    else if (/^https?:\/\//.test(m[4])) {
      out.push(<a key={m.index} href={m[4]} target="_blank" rel="noopener noreferrer" className="link">{m[3]}</a>);
    } else if (o.onFile && !/^[a-z]+:/i.test(m[4]) && /\.(md|csv)(#.*)?$/.test(m[4])) {
      const path = resolve(o.base ?? "", m[4]);
      out.push(<button key={m.index} type="button" onClick={() => o.onFile!(path)} className="link text-start">{m[3]}</button>);
    } else out.push(m[3]);
    last = m.index + m[0].length;
  }
  if (last < s.length) out.push(s.slice(last));
  return out.map((part, i) => typeof part === "string"
    ? part.split("\n").map((l, j) => <Fragment key={`${i}-${j}`}>{j > 0 && <br />}{l}</Fragment>) : part);
}

/** One line of the team's Markdown (a table cell, a list item), same rules. */
export function MdInline({ text, base, onFile }: { text: string; base?: string; onFile?: (path: string) => void }) {
  return <>{inline(text, { base, onFile })}</>;
}
