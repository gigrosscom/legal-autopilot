"""Document assembly: DOCX template (docxtpl) → DOCX → PDF (LibreOffice headless).

Core guarantees, independent of the template:
  * the AI label from the pack is on every page footer — the one closing line (owner 01.10 «оставить одну»; owner
    02.10: only «Подготовлено с помощью ИИ (Konsiliér AI).», without «Проверьте данные перед подачей»);
  * `finish` — the last pass over every paragraph's text (gendered forms, amounts in words).
"""

from __future__ import annotations

import io
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable, Protocol

from docx import Document
from docx.shared import Pt
from docxtpl import DocxTemplate

from . import docstyle
from .docstyle import DocStyle

log = logging.getLogger(__name__)


def render_docx(template_path: Path, context: dict[str, Any], ai_label: str,
                draft_disclaimer: str | None, finish: Callable[[str], str] | None = None,
                style: DocStyle | None = None, lang: str = "ru", drop_empty: tuple[str, ...] = ()) -> bytes:
    """`draft_disclaimer` (a scenario not reviewed by a lawyer) is no longer printed: the document carries one AI line
    in the footer (owner 01.10); the argument stays for the callers."""
    tpl = DocxTemplate(str(template_path))
    tpl.render(context, autoescape=True)
    buf = io.BytesIO()
    tpl.save(buf)

    doc = Document(io.BytesIO(buf.getvalue()))
    if drop_empty:  # PM 02.10: a label left with nothing after it («Правовое основание:») is not printed
        empty = {f"{label.strip().lower()}:" for label in drop_empty}
        for p in list(doc.paragraphs):
            if p.text.strip().lower() in empty:
                p._element.getparent().remove(p._element)
    if finish is not None:
        paragraphs = list(doc.paragraphs) + [p for t in doc.tables for row in t.rows for c in row.cells for p in c.paragraphs]
        for p in paragraphs:
            text = p.text
            new = finish(text) if text else text
            if new != text and p.runs:
                p.runs[0].text = new
                for r in p.runs[1:]:
                    r.text = ""
    if style is not None:  # the official layout; the AI line is the last small line of the last page
        docstyle.apply(doc, style, ai_label, lang)
    elif ai_label:
        for section in doc.sections:
            fp = section.footer.add_paragraph()
            frun = fp.add_run(ai_label)
            frun.font.size = Pt(7)
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


def docx_text(data: bytes) -> str:
    """Plain text of a DOCX (body + footers) — used by tests and admin preview."""
    doc = Document(io.BytesIO(data))
    parts = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            parts.extend(cell.text for cell in row.cells)
    for section in doc.sections:
        parts.extend(p.text for p in section.footer.paragraphs)
    return "\n".join(parts)


class PdfConverter(Protocol):
    def convert(self, docx: bytes) -> bytes | None: ...


class NullPdfConverter:
    def convert(self, docx: bytes) -> bytes | None:
        return None


class LibreOfficeConverter:
    def __init__(self, soffice_bin: str = "soffice", timeout: int = 90):
        self.soffice_bin = soffice_bin
        self.timeout = timeout

    def available(self) -> bool:
        return shutil.which(self.soffice_bin) is not None

    def convert(self, docx: bytes) -> bytes | None:
        if not self.available():
            log.warning("LibreOffice (%s) not found — PDF skipped", self.soffice_bin)
            return None
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "document.docx"
            src.write_bytes(docx)
            profile = Path(tmp) / "profile"
            cmd = [self.soffice_bin, f"-env:UserInstallation=file://{profile}", "--headless",
                   "--convert-to", "pdf", "--outdir", tmp, str(src)]
            try:
                subprocess.run(cmd, check=True, capture_output=True, timeout=self.timeout)
            except (subprocess.SubprocessError, OSError) as e:
                log.error("PDF conversion failed: %s", e)
                return None
            pdf = Path(tmp) / "document.pdf"
            return pdf.read_bytes() if pdf.exists() else None


def build_pdf_converter(settings) -> PdfConverter:
    if not settings.soffice_bin:
        return NullPdfConverter()
    return LibreOfficeConverter(settings.soffice_bin)
