"""Official layout of every generated document (owner 01.10): applied to the DOCX after the template is filled, so
each template keeps only its words. The numbers come from the pack (document_style) — the lawyer tunes them there.

The rules are the lawyer's (team/legal-drafts/document-rules.md, D-23…D-31, Правила документирования, приказ МКС
№ 236): A4, margins 25/15/20/20 mm; Times New Roman 14 (attachments 12; the PDF uses the metric-equivalent Liberation
Serif, every pack's letters included), single spacing, first line 1.25 cm, justified; the «Кому» block on the right in bold,
«От кого» plain; the document's name in bold capitals centred, the heading «о …» bold under it; «прошу:» bold with
demands «1.»; «Приложение:» numbered; the date in words on the left, «И. Фамилия» on the right; page numbers from
page 2 at the top centre; one small AI line at the end."""
from __future__ import annotations

import re
from dataclasses import dataclass

from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Mm, Pt, RGBColor


@dataclass(frozen=True)
class DocStyle:
    font: str = "Times New Roman"
    size: float = 14
    line_spacing: float = 1.0
    first_line_cm: float = 1.25
    margin_left_mm: float = 25  # D-23
    margin_right_mm: float = 15
    margin_top_mm: float = 20
    margin_bottom_mm: float = 20
    header_indent_cm: float = 8.0  # the «Кому / От» block starts this far from the left margin
    page_numbers_from: int = 2  # D-31: from page 2, at the top centre
    signature: str = "initial_surname"  # D-29: «Е. Ахметов»; initials → «Е. С. Ахметов»; full → ФИО полностью
    small_size: float = 12  # D-24: attachments (and tables) in 12 pt
    date_in_words: bool = True  # D-29: «1 октября 2026 года»
    ai_line_size: float = 8


_ASK = re.compile(r"((?:прошу|требую)(?:\s+\w+){0,2}|(?:сұраймын|талап етемін)|I (?:ask|request|demand)(?:\s+\w+){0,2})\s*:\s*$", re.I)
_ANNEX = re.compile(r"^\s*(приложени[яе]|қосымша(лар)?|attachments?)\s*:?\s*$", re.I)
_BASIS = re.compile(r"^\s*(правовое основание|құқықтық негіз|legal basis)", re.I)
_FROM = re.compile(r"^\s*(от|кімнен|from)\s*:", re.I)
_SIGN = re.compile(r"^\s*(дата|күні|date)\s*:\s*(?P<date>\S+)\s+.*?(?:/\s*(?P<name>.+))?$", re.I)


def initials(full_name: str) -> str:
    """«Ахметов Ерлан Серикович» → «Е. С. Ахметов»; one word stays as it is."""
    words = [w for w in full_name.split() if w]
    if len(words) < 2:
        return full_name.strip()
    return " ".join(f"{w[0].upper()}." for w in words[1:3]) + " " + words[0]


def initial_surname(full_name: str) -> str:
    """«Ахметов Ерлан Серикович» → «Е. Ахметов» (D-29)."""
    words = [w for w in full_name.split() if w]
    return f"{words[1][0].upper()}. {words[0]}" if len(words) >= 2 else full_name.strip()


MONTHS = {"ru": ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября",
                 "ноября", "декабря"],
          "kk": ["қаңтар", "ақпан", "наурыз", "сәуір", "мамыр", "маусым", "шілде", "тамыз", "қыркүйек", "қазан",
                 "қараша", "желтоқсан"]}


def date_words(ddmmyyyy: str, lang: str) -> str:
    """«01.10.2026» → «1 октября 2026 года» (ru) / «2026 жылғы 1 қазан» (kk); another language or form: as is."""
    m = re.match(r"^(\d{2})\.(\d{2})\.(\d{4})$", ddmmyyyy.strip())
    if not m or lang not in MONTHS:
        return ddmmyyyy
    d, mo, y = int(m.group(1)), int(m.group(2)), m.group(3)
    return f"{d} {MONTHS['ru'][mo - 1]} {y} года" if lang == "ru" else f"{y} жылғы {d} {MONTHS['kk'][mo - 1]}"


def _is_title(text: str) -> bool:
    t = text.strip()
    letters = [c for c in t if c.isalpha()]
    return bool(letters) and len(t) <= 80 and ":" not in t and all(c.isupper() for c in letters) and len(letters) >= 4


def _font(run, style: DocStyle, size: float | None = None, bold: bool | None = None) -> None:
    run.font.name = style.font
    rpr = run._element.get_or_add_rPr()
    fonts = rpr.find(qn("w:rFonts"))
    if fonts is None:
        fonts = OxmlElement("w:rFonts")
        rpr.insert(0, fonts)
    for attr in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        fonts.set(qn(attr), style.font)
    run.font.size = Pt(size or style.size)
    run.font.color.rgb = RGBColor(0, 0, 0)
    if bold is not None:
        run.font.bold = bold


def _set_text(p, text: str) -> None:
    if p.runs:
        p.runs[0].text = text
        for r in p.runs[1:]:
            r.text = ""
    else:
        p.add_run(text)


def _page_number(paragraph) -> None:
    run = paragraph.add_run()
    for kind, text in (("begin", None), (None, "PAGE"), ("end", None)):
        if kind:
            el = OxmlElement("w:fldChar")
            el.set(qn("w:fldCharType"), kind)
        else:
            el = OxmlElement("w:instrText")
            el.set(qn("xml:space"), "preserve")
            el.text = text
        run._element.append(el)


def apply(doc, style: DocStyle, ai_label: str, lang: str = "ru") -> None:
    text_width = Mm(210 - style.margin_left_mm - style.margin_right_mm)
    for section in doc.sections:
        section.page_width, section.page_height = Mm(210), Mm(297)
        section.left_margin, section.right_margin = Mm(style.margin_left_mm), Mm(style.margin_right_mm)
        section.top_margin, section.bottom_margin = Mm(style.margin_top_mm), Mm(style.margin_bottom_mm)
        for p in list(section.footer.paragraphs):
            _set_text(p, "")
        section.different_first_page_header_footer = style.page_numbers_from >= 2
        hp = section.header.paragraphs[0] if section.header.paragraphs else section.header.add_paragraph()
        hp.alignment = WD_ALIGN_PARAGRAPH.CENTER  # D-31: from page 2, at the top centre, no dashes
        _page_number(hp)
        for r in hp.runs:
            _font(r, style, size=style.small_size)
    normal = doc.styles["Normal"]
    normal.font.name, normal.font.size = style.font, Pt(style.size)
    normal.paragraph_format.space_before, normal.paragraph_format.space_after = Pt(0), Pt(0)

    paragraphs = list(doc.paragraphs)
    while paragraphs and not paragraphs[-1].text.strip():  # trailing blanks of the template
        paragraphs[-1]._element.getparent().remove(paragraphs[-1]._element)
        paragraphs.pop()
    title = next((i for i, p in enumerate(paragraphs) if _is_title(p.text)), None)
    mode = "header" if title is not None else "body"
    to_block = True
    demands: list = []
    for i, p in enumerate(paragraphs):
        text = p.text
        if not text.strip() and mode not in ("header", "subtitle"):
            p._element.getparent().remove(p._element)  # the spacing is the layout's, not the template's blank lines
            continue
        pf = p.paragraph_format
        pf.line_spacing = style.line_spacing
        pf.space_before, pf.space_after = Pt(0), Pt(0)
        bold = None
        if title is not None and i == title:
            mode = "subtitle"
            p.alignment, pf.first_line_indent, pf.left_indent = WD_ALIGN_PARAGRAPH.CENTER, Cm(0), Cm(0)
            pf.space_before, pf.space_after = Pt(style.size), Pt(0)
            bold = True
        elif mode == "header":
            p.alignment, pf.first_line_indent, pf.left_indent = WD_ALIGN_PARAGRAPH.LEFT, Cm(0), Cm(style.header_indent_cm)
            if _FROM.match(text):
                to_block = False
            bold = True if to_block else None  # D-26: «Кому» in bold, «От кого» plain
        elif mode == "subtitle" and text.strip():
            p.alignment, pf.first_line_indent = WD_ALIGN_PARAGRAPH.CENTER, Cm(0)
            pf.space_after = Pt(style.size)
            bold, mode = True, "body"  # D-27: the heading «о …» in bold too
        elif _ASK.search(text):
            p.alignment, pf.first_line_indent = WD_ALIGN_PARAGRAPH.LEFT, Cm(style.first_line_cm)
            bold, mode = True, "demands"
        elif mode == "demands" and text.strip() and not _BASIS.match(text) and not _ANNEX.match(text):
            demands.append(p)
            p.alignment, pf.first_line_indent = WD_ALIGN_PARAGRAPH.JUSTIFY, Cm(style.first_line_cm)
        elif _ANNEX.match(text):
            if lang == "ru":
                _set_text(p, "Приложение:")  # D-30
            p.alignment, pf.first_line_indent = WD_ALIGN_PARAGRAPH.LEFT, Cm(style.first_line_cm)
            pf.space_before = Pt(style.size / 2)
            mode = "annex"
        elif (m := _SIGN.match(text)) is not None:
            name = (m.group("name") or "").strip()
            if name:
                name = {"initials": initials, "initial_surname": initial_surname}.get(style.signature, str)(name)
            day = date_words(m.group("date"), lang) if style.date_in_words else m.group("date")
            _set_text(p, f"{day}\t______________ {name}" if name else f"{day}\t______________")
            p.alignment, pf.first_line_indent, pf.left_indent = WD_ALIGN_PARAGRAPH.LEFT, Cm(0), Cm(0)
            pf.tab_stops.add_tab_stop(text_width, WD_TAB_ALIGNMENT.RIGHT)
            pf.space_before = Pt(style.size)
            mode = "sign"
        elif mode == "annex":
            p.alignment, pf.first_line_indent = WD_ALIGN_PARAGRAPH.LEFT, Cm(style.first_line_cm)
            for r in p.runs:
                _font(r, style, size=style.small_size)
            continue
        else:
            if _BASIS.match(text):
                mode = "body"
            p.alignment, pf.first_line_indent = WD_ALIGN_PARAGRAPH.JUSTIFY, Cm(style.first_line_cm)
        for r in p.runs:
            _font(r, style, bold=bold)
    _number(demands, style)
    if ai_label:
        last = doc.add_paragraph()
        last.paragraph_format.space_before = Pt(style.size)
        _font(last.add_run(ai_label), style, size=style.ai_line_size)
    for t in doc.tables:
        for row in t.rows:
            for c in row.cells:
                for p in c.paragraphs:
                    for r in p.runs:
                        _font(r, style)


def _number(paragraphs: list, style: DocStyle) -> None:
    """The demands as a numbered list: «1. Вернуть …». One paragraph of several demands joined by «;» is split."""
    items: list[str] = []
    for p in paragraphs:
        text = p.text.strip()
        if re.match(r"^\d+[.)]\s", text):
            items.append(re.sub(r"^\d+[.)]\s+", "", text))
        else:
            items += [x.strip() for x in re.split(r";\s+(?=[^\d])", text) if x.strip()]
    if not paragraphs or not items:
        return
    first, rest = paragraphs[0], paragraphs[1:]
    for p in rest:
        p._element.getparent().remove(p._element)
    texts = [f"{n}. {s[:1].upper()}{s[1:].rstrip(';')}" + ("." if not s.rstrip().endswith((".", ";")) else "")
             for n, s in enumerate(items, 1)]
    _set_text(first, texts[0])
    anchor = first
    for t in texts[1:]:
        new = OxmlElement("w:p")
        anchor._element.addnext(new)
        from docx.text.paragraph import Paragraph
        para = Paragraph(new, first._parent)
        para.paragraph_format.first_line_indent = Cm(style.first_line_cm)
        para.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        para.paragraph_format.line_spacing = style.line_spacing
        para.paragraph_format.space_before, para.paragraph_format.space_after = Pt(0), Pt(0)
        _font(para.add_run(t), style)
        anchor = para
