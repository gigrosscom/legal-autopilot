import { Fragment, type ReactNode } from "react";

/**
 * The little Markdown the chat model writes — paragraphs, numbered and bulleted lists, **bold**, *italic*, headings
 * and [links](https://…) — rendered as React elements (never as HTML), so a reply can hold no markup of its own.
 */
export function Markdown({ text }: { text: string }) {
  const blocks: ReactNode[] = [];
  let list: { ordered: boolean; items: string[]; start: number } | null = null;
  let para: string[] = [];
  const flushPara = () => {
    if (para.length) blocks.push(<p key={blocks.length}>{inline(para.join("\n"))}</p>);
    para = [];
  };
  const flushList = () => {
    if (!list) return;
    const { ordered, items, start } = list;
    const Tag = ordered ? "ol" : "ul";
    blocks.push(
      <Tag key={blocks.length} start={ordered ? start : undefined}
        className={`space-y-1.5 ps-6 ${ordered ? "list-decimal" : "list-disc"} marker:text-muted`}>
        {items.map((it, i) => <li key={i} className="ps-1">{inline(it)}</li>)}
      </Tag>);
    list = null;
  };

  for (const raw of text.split("\n")) {
    const line = raw.trimEnd();
    const ol = line.match(/^\s*(\d+)[.)]\s+(.*)$/);
    const ul = line.match(/^\s*[-*•]\s+(.*)$/);
    const h = line.match(/^#{1,4}\s+(.*)$/);
    if (ol || ul) {
      flushPara();
      const ordered = !!ol;
      if (!list || list.ordered !== ordered) { flushList(); list = { ordered, items: [], start: ol ? Number(ol[1]) : 1 }; }
      list.items.push(ol ? ol[2] : ul![1]);
    } else if (h) {
      flushPara(); flushList();
      blocks.push(<p key={blocks.length} className="font-semibold">{inline(h[1])}</p>);
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

/** **bold**, *italic* and [text](https://…) inside a line; line breaks kept. */
function inline(s: string): ReactNode {
  const out: ReactNode[] = [];
  const re = /\*\*([^*]+)\*\*|(?<![*\w])\*([^*\n]+)\*(?![*\w])|\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g;
  let last = 0, m: RegExpExecArray | null;
  while ((m = re.exec(s))) {
    if (m.index > last) out.push(s.slice(last, m.index));
    if (m[1]) out.push(<strong key={m.index} className="font-semibold">{m[1]}</strong>);
    else if (m[2]) out.push(<em key={m.index}>{m[2]}</em>);
    else out.push(<a key={m.index} href={m[4]} target="_blank" rel="noopener noreferrer" className="link">{m[3]}</a>);
    last = m.index + m[0].length;
  }
  if (last < s.length) out.push(s.slice(last));
  return out.map((part, i) => typeof part === "string"
    ? part.split("\n").map((l, j) => <Fragment key={`${i}-${j}`}>{j > 0 && <br />}{l}</Fragment>) : part);
}
