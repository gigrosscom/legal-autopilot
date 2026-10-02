"""Documents already given with the phrase the owner forbade (02.10): «Проверьте данные перед подачей» /
«Проверьте сведения перед подачей» (new ones are without it since #178). The stored DOCX is cleaned in place — only
that phrase goes, the rest of the text stays as it was given — and the PDF is made again from it."""

from __future__ import annotations

import io
from typing import Any

from docx import Document

OLD_PHRASES = ("Проверьте данные перед подачей.", "Проверьте сведения перед подачей.",
               "Проверьте данные перед подачей", "Проверьте сведения перед подачей")


def _paragraphs(doc: Any) -> list[Any]:
    out = list(doc.paragraphs) + [p for t in doc.tables for r in t.rows for c in r.cells for p in c.paragraphs]
    for s in doc.sections:
        for part in (s.footer, s.header, s.first_page_footer, s.first_page_header):
            out += list(part.paragraphs)
    return out


def strip_old_phrases(data: bytes) -> bytes | None:
    """The DOCX without the forbidden phrase, or None when it has none."""
    doc = Document(io.BytesIO(data))
    changed = False
    for p in _paragraphs(doc):
        text = p.text
        if not any(ph in text for ph in OLD_PHRASES):
            continue
        new = text
        for ph in OLD_PHRASES:
            new = new.replace(ph, "")
        new = " ".join(new.split())
        if not new:
            p._element.getparent().remove(p._element)
        elif p.runs:
            p.runs[0].text = new
            for r in p.runs[1:]:
                r.text = ""
        changed = True
    if not changed:
        return None
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


def reissue_all(session: Any, storage: Any, pdf: Any, apply: bool) -> dict[str, int]:
    """Every stored document: cleaned (apply=True) or only counted. The PDF is made again from the cleaned DOCX."""
    from sqlalchemy import select

    from .models import Action

    seen = cleaned = pdfs = 0
    for action in session.scalars(select(Action).where(Action.docx_key.is_not(None))).all():
        seen += 1
        try:
            fixed = strip_old_phrases(storage.get(action.docx_key))
        except Exception:  # noqa: BLE001 — a file that cannot be read is reported, not fatal
            continue
        if fixed is None:
            continue
        cleaned += 1
        if not apply:
            continue
        storage.put(action.docx_key, fixed,
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        made = pdf.convert(fixed) if pdf is not None else None
        if made:
            key = action.pdf_key or action.docx_key.rsplit(".", 1)[0] + ".pdf"
            action.pdf_key = storage.put(key, made, "application/pdf")
            pdfs += 1
    return {"documents": seen, "with_phrase": cleaned, "pdf_remade": pdfs, "applied": int(apply)}
