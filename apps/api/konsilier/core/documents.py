"""Document assembly: DOCX template (docxtpl) → DOCX → PDF (LibreOffice headless).

Core guarantees, independent of the template:
  * the AI label from the pack is appended to the body and to every page footer;
  * a neutral note (compliance.draft_disclaimer, no "draft" wording) is appended when the scenario is not
    reviewed by a lawyer.
"""

from __future__ import annotations

import io
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Protocol

from docx import Document
from docx.shared import Pt
from docxtpl import DocxTemplate

log = logging.getLogger(__name__)


def render_docx(template_path: Path, context: dict[str, Any], ai_label: str,
                draft_disclaimer: str | None) -> bytes:
    tpl = DocxTemplate(str(template_path))
    tpl.render(context, autoescape=True)
    buf = io.BytesIO()
    tpl.save(buf)

    doc = Document(io.BytesIO(buf.getvalue()))
    if draft_disclaimer:
        p = doc.add_paragraph()
        run = p.add_run(draft_disclaimer)
        run.italic = True
        run.font.size = Pt(8)
    if not draft_disclaimer and ai_label:  # QA BUG-14: one closing note in the body; the AI label stays in the footer
        p = doc.add_paragraph()
        run = p.add_run(ai_label)
        run.italic = True
        run.font.size = Pt(8)
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
