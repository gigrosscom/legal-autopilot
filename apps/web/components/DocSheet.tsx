import { Fragment, type ReactNode } from "react";
import { Icon } from "@/components/ui";

/** Owner 02.10: the draft looks like the official document it becomes (the PDF's layout, apps/api core/docstyle.py):
 * a white A4 sheet with margins, Times New Roman, the «Кому / От» block on the right, the name of the document bold
 * and centred, the «о …» heading under it, paragraphs justified with a first-line indent. The server sends the
 * draft as plain lines (one per paragraph); the parts are found here the way docstyle finds them, so the text
 * itself is not changed. The sheet stays white in the dark theme — it is paper. */

const TITLE_MAX = 80;
const FROM = /^\s*(от|кімнен|from)\s*:/i;
const LABEL = /^(\s*(?:кому|от|кімге|кімнен|to|from)\s*:)(.*)$/i;
const ASK = /((?:прошу|требую)(?:\s+\S+){0,2}|сұраймын|талап етемін|I (?:ask|request|demand)(?:\s+\S+){0,2})\s*:\s*$/i;
const ANNEX = /^\s*(приложени[яе]|қосымша(лар)?|attachments?)\s*:?\s*$/i;
const BASIS = /^\s*(правовое основание|құқықтық негіз|legal basis)/i;

function isTitle(line: string): boolean {
  const t = line.trim();
  const letters = [...t].filter((c) => c.toLowerCase() !== c.toUpperCase());
  return letters.length >= 4 && t.length <= TITLE_MAX && !t.includes(":") && letters.every((c) => c === c.toUpperCase());
}

/** «[Название продавца]» — a blank still to fill: marked like a highlighter on paper. */
function withBlanks(text: string): ReactNode {
  const parts = text.split(/(\[[^\]\n]+\])/);
  return parts.map((p, i) => (i % 2 ? <mark key={i} className="rounded-[2px] bg-[#fff1b8] px-0.5 text-inherit">{p}</mark> : <Fragment key={i}>{p}</Fragment>));
}

type Kind = "to" | "from" | "title" | "subtitle" | "ask" | "item" | "annex" | "annexItem" | "sign" | "body";
type Line = { text: string; kind: Kind; hidden: boolean };

function parse(visible: string, hidden: string): Line[] {
  const full = visible + hidden;
  const lines: { text: string; hidden: boolean }[] = [];
  let at = 0;
  for (const text of full.split("\n")) {
    // a line is blurred once it starts in the hidden part (the server cuts the draft at a line break)
    if (text.trim()) lines.push({ text, hidden: at >= visible.length });
    at += text.length + 1;
  }
  const title = lines.findIndex((l) => !l.hidden && isTitle(l.text));
  let mode: "to" | "from" | "subtitle" | "body" | "demands" | "annex" | "sign" = title >= 0 ? "to" : "body";
  return lines.map((l, i): Line => {
    const t = l.text;
    if (i === title) { mode = "subtitle"; return { ...l, kind: "title" }; }
    if (mode === "to" || mode === "from") {
      if (FROM.test(t)) mode = "from";
      return { ...l, kind: mode };
    }
    if (mode === "subtitle") { mode = "body"; return { ...l, kind: "subtitle" }; }
    if (t.includes("\t")) { mode = "sign"; return { ...l, kind: "sign" }; }
    if (ANNEX.test(t)) { mode = "annex"; return { ...l, kind: "annex" }; }
    if (mode === "annex") return { ...l, kind: "annexItem" };
    if (ASK.test(t)) { mode = "demands"; return { ...l, kind: "ask" }; }
    if (BASIS.test(t)) { mode = "body"; return { ...l, kind: "body" }; }
    return { ...l, kind: mode === "demands" ? "item" : "body" };
  });
}

function Para({ line }: { line: Line }) {
  const { text, kind } = line;
  switch (kind) {
    case "to":
    case "from": {
      const m = text.match(LABEL);
      return <p className="break-words">{m ? <><b>{m[1]}</b>{withBlanks(m[2])}</> : withBlanks(text)}</p>;
    }
    case "title":
      // the letter spacing also follows the last letter: the same padding on the left keeps the word centred
      return <p className="mt-[1.4em] ps-[0.25em] text-center font-bold tracking-[0.25em]">{text.trim()}</p>;
    case "subtitle":
      return <p className="mb-[1em] text-center font-bold [text-wrap:balance]">{withBlanks(text)}</p>;
    case "ask":
      return <p className="indent-[7.5%] font-bold">{withBlanks(text)}</p>;
    case "annex":
      return <p className="mt-[0.5em] indent-[7.5%]">{withBlanks(text)}</p>;
    case "annexItem":
      return <p className="indent-[7.5%] text-[0.86em]">{withBlanks(text)}</p>;
    case "sign": {
      const [left, ...right] = text.split("\t");
      return (
        <p className="mt-[1.4em] flex flex-wrap justify-between gap-x-4">
          <span>{withBlanks(left)}</span><span className="ms-auto">{withBlanks(right.join(" ").trim())}</span>
        </p>
      );
    }
    default:
      return <p className="indent-[7.5%] text-justify [hyphens:auto]">{withBlanks(text)}</p>;
  }
}

const SERIF = "'Times New Roman', 'Liberation Serif', Tinos, 'PT Serif', 'Noto Serif', Georgia, serif";

export function DocSheet({ visible, hidden, locked }: { visible: string; hidden: string; locked: string }) {
  const lines = parse(visible, hidden);
  const open = lines.filter((l) => !l.hidden);
  const shut = lines.filter((l) => l.hidden);
  const header = open.filter((l) => l.kind === "to" || l.kind === "from");
  const rest = open.filter((l) => l.kind !== "to" && l.kind !== "from");
  return (
    <div
      className="mx-auto aspect-[210/297] w-full max-w-[42rem] rounded-[4px] bg-white text-[#111] shadow-[0_1px_2px_rgba(0,0,0,0.08),0_8px_24px_rgba(0,0,0,0.12)] ring-1 ring-black/5"
    >
      {/* the A4 margins 20/15/20/25 mm, scaled to the sheet's width */}
      <div style={{ fontFamily: SERIF }} className="px-[7%] py-[8%] text-[13px] sm:py-[9.5%] sm:ps-[11.9%] sm:pe-[7.1%] leading-[1.4] min-[400px]:text-[14px] sm:text-[15px]">
        {header.length > 0 && (
          <div className="ms-auto w-[60%] sm:w-1/2">
            {header.map((l, i) => <Para key={i} line={l} />)}
          </div>
        )}
        {rest.map((l, i) => <Para key={i} line={l} />)}
        {shut.length > 0 && (
          // the start of the rest, blurred, fading into the paper; the lock sits on it, not at the foot of the page
          <div className="relative">
            <div aria-hidden className="pointer-events-none max-h-[10em] select-none overflow-hidden blur-[4px]">
              {shut.map((l, i) => <Para key={i} line={l} />)}
            </div>
            <div className="absolute -inset-x-[8%] inset-y-0 flex items-end justify-center bg-gradient-to-b from-white/0 via-white/70 to-white pb-[1.4em]">
              <p className="inline-flex min-h-11 items-center gap-2 whitespace-nowrap rounded-full bg-[#1d1d1f] px-4 font-sans text-[13px] max-[379px]:gap-1.5 max-[379px]:px-3 max-[379px]:text-[12px] font-semibold text-white shadow-[0_4px_12px_rgba(0,0,0,0.18)]">
                <Icon name="lock" size={14} className="shrink-0" />{locked}
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
