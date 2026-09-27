"""Generate the DOCX templates of the KZ pack (docxtpl / Jinja2 syntax).

Templates are pack DATA: a lawyer can open and edit them in Word directly.
This script only bootstraps the first versions:

    python scripts/build_kz_templates.py

Available context (see core/engine.py::document_context):
    title, f.<field>, applicant.{name,id}, addressee.{name,id,address,email},
    narrative, demands, norm_refs, evidence, previous_actions, date, currency
"""

from __future__ import annotations

import sys
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt

ROOT = Path(__file__).resolve().parents[1] / "packs" / "kz" / "templates"

NORMS = ("{% for r in norm_refs %}{{ '[норма уточняется юристом]' if 'TODO' in r else r }}"
         "{% if not loop.last %}; {% endif %}{% endfor %}")


def _doc() -> Document:
    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Times New Roman"
    style.font.size = Pt(12)
    return doc


def _right(doc: Document, text: str) -> None:
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    p.add_run(text)


def _center(doc: Document, text: str, bold: bool = True) -> None:
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(text)
    run.bold = bold


def _para(doc: Document, text: str, bold: bool = False) -> None:
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    run = p.add_run(text)
    run.bold = bold


def _header(doc: Document, *, extra_addressee: str = "", extra_applicant: str = "") -> None:
    _right(doc, "Кому: {{ addressee.name }}")
    _right(doc, "{% if addressee.id %}БИН: {{ addressee.id }}{% endif %}")
    if extra_addressee:
        _right(doc, extra_addressee)
    _right(doc, "От: {{ applicant.name }}")
    _right(doc, "{% if applicant.id %}ИИН: {{ applicant.id }}{% endif %}")
    _right(doc, "Тел.: {{ f.applicant_phone }}")
    if extra_applicant:
        _right(doc, extra_applicant)


def _tail(doc: Document, demand_intro: str) -> None:
    _para(doc, demand_intro, bold=True)
    _para(doc, "{{ demands }}")
    _para(doc, "Правовое основание: " + NORMS)
    doc.add_paragraph("{%p if evidence %}")
    _para(doc, "Приложения:", bold=True)
    doc.add_paragraph("{%p for e in evidence %}")
    doc.add_paragraph("{{ loop.index }}. {{ e }}")
    doc.add_paragraph("{%p endfor %}")
    doc.add_paragraph("{%p endif %}")
    doc.add_paragraph("")
    doc.add_paragraph("Дата: {{ date }}                    Подпись: ______________ / {{ applicant.name }}")


def _previous(doc: Document) -> None:
    doc.add_paragraph("{%p if previous_actions %}")
    _para(doc, "Ранее предпринятые действия:", bold=True)
    doc.add_paragraph("{%p for a in previous_actions %}")
    doc.add_paragraph("— {{ a.title }} (направлено {{ a.date }}): {{ a.response }}.")
    doc.add_paragraph("{%p endfor %}")
    doc.add_paragraph("{%p endif %}")


def claim_seller() -> Document:
    doc = _doc()
    _header(doc)
    _center(doc, "ПРЕТЕНЗИЯ")
    _center(doc, "о возврате уплаченной денежной суммы", bold=False)
    _para(doc, "{{ f.purchase_date }} мной приобретен(а) «{{ f.goods_description }}» у {{ addressee.name }} "
               "на сумму {{ f.amount }} {{ currency }}.")
    _para(doc, "{{ narrative }}")
    _tail(doc, "На основании изложенного прошу:")
    return doc


def complaint_authority() -> Document:
    doc = _doc()
    _header(doc)
    _center(doc, "ЖАЛОБА")
    _center(doc, "о нарушении прав потребителя", bold=False)
    _para(doc, "{{ f.purchase_date }} мной приобретен(а) «{{ f.goods_description }}» у {{ f.seller_name }}"
               "{% if f.seller_bin %} (БИН {{ f.seller_bin }}){% endif %} на сумму {{ f.amount }} {{ currency }}.")
    _para(doc, "{{ narrative }}")
    _previous(doc)
    _tail(doc, "Прошу:")
    return doc


def statement_lender() -> Document:
    doc = _doc()
    _header(doc)
    _center(doc, "ЗАЯВЛЕНИЕ")
    _center(doc, "об оформлении займа без волеизъявления заемщика (мошенничество)", bold=False)
    _para(doc, "Мне стало известно, что {{ f.loan_date }} на мое имя в {{ addressee.name }} оформлен заем "
               "на сумму {{ f.amount }} {{ currency }}{% if f.contract_number %} (договор № {{ f.contract_number }})"
               "{% endif %}. Данный заем я не оформлял(а), согласия на его оформление не давал(а), денежные "
               "средства не получал(а) и ими не распоряжался(ась).")
    _para(doc, "{{ narrative }}")
    _para(doc, "{% if f.police_report_number %}По факту мошенничества я обратился(ась) в органы полиции: "
               "{{ f.police_report_number }}.{% endif %}")
    _tail(doc, "Прошу:")
    return doc


def complaint_arrf() -> Document:
    doc = _doc()
    _header(doc)
    _center(doc, "ЖАЛОБА")
    _center(doc, "на действия финансовой организации", bold=False)
    _para(doc, "{{ f.loan_date }} на мое имя в {{ f.lender_name }}{% if f.lender_bin %} (БИН {{ f.lender_bin }})"
               "{% endif %} без моего волеизъявления оформлен заем на сумму {{ f.amount }} {{ currency }}"
               "{% if f.contract_number %} (договор № {{ f.contract_number }}){% endif %}.")
    _para(doc, "{{ narrative }}")
    _para(doc, "{% if f.police_report_number %}Обращение в полицию: {{ f.police_report_number }}.{% endif %}")
    _previous(doc)
    _tail(doc, "Прошу:")
    return doc


GENERIC_NORMS = ("{% for r in norm_refs %}{{ '[норма: уточнит юрист]' if 'TODO' in r else r }}"
                 "{% if not loop.last %}; {% endif %}{% endfor %}")


def generic(title: str, subtitle: str, demand_intro: str) -> Document:
    """Universal document (coverage level 2): norms/deadlines only from pack data, else a placeholder."""
    doc = _doc()
    _header(doc, extra_applicant="Адрес: {{ f.applicant_address }}")
    _center(doc, title)
    _center(doc, subtitle, bold=False)
    _para(doc, "Ответчик / лицо, на действия которого подается обращение: {{ f.respondent_name }}.")
    _para(doc, "{% if f.event_date %}Дата события: {{ f.event_date }}.{% endif %}"
               "{% if f.amount %} Сумма требований: {{ f.amount }} {{ currency }}.{% endif %}")
    _para(doc, "{{ narrative }}")
    _previous(doc)
    _para(doc, demand_intro, bold=True)
    _para(doc, "{{ demands }}")
    _para(doc, "Правовое основание: " + GENERIC_NORMS)
    doc.add_paragraph("{%p if evidence %}")
    _para(doc, "Приложения:", bold=True)
    doc.add_paragraph("{%p for e in evidence %}")
    doc.add_paragraph("{{ loop.index }}. {{ e }}")
    doc.add_paragraph("{%p endfor %}")
    doc.add_paragraph("{%p endif %}")
    doc.add_paragraph("")
    doc.add_paragraph("Дата: {{ date }}                    Подпись: ______________ / {{ applicant.name }}")
    return doc


def claim_letter() -> Document:
    """Universal pre-trial claim to the other party itself (seller, bank, employer, landlord, debtor)."""
    doc = _doc()
    _header(doc, extra_applicant="Адрес: {{ f.applicant_address }}")
    _center(doc, "ПРЕТЕНЗИЯ")
    _center(doc, "(досудебная)", bold=False)
    _para(doc, "{% if f.event_date %}Дата события: {{ f.event_date }}.{% endif %}"
               "{% if f.amount %} Сумма требований: {{ f.amount }} {{ currency }}.{% endif %}")
    _para(doc, "{{ narrative }}")
    _previous(doc)
    _para(doc, "На основании изложенного требую:", bold=True)
    _para(doc, "{{ demands }}")
    _para(doc, "Правовое основание: " + GENERIC_NORMS)
    _para(doc, "Прошу дать письменный ответ на претензию. Если требования не будут удовлетворены, я буду вынужден(а) "
               "обратиться в уполномоченный государственный орган и (или) в суд для защиты своих прав.")
    doc.add_paragraph("{%p if evidence %}")
    _para(doc, "Приложения:", bold=True)
    doc.add_paragraph("{%p for e in evidence %}")
    doc.add_paragraph("{{ loop.index }}. {{ e }}")
    doc.add_paragraph("{%p endfor %}")
    doc.add_paragraph("{%p endif %}")
    doc.add_paragraph("")
    doc.add_paragraph("Дата: {{ date }}                    Подпись: ______________ / {{ applicant.name }}")
    return doc


def main() -> None:
    out = {
        "consumer/claim_seller.docx": claim_seller,
        "consumer/complaint_authority.docx": complaint_authority,
        "money/statement_lender.docx": statement_lender,
        "money/complaint_arrf.docx": complaint_arrf,
        "generic/complaint.docx": lambda: generic("ЖАЛОБА", "{{ title }}", "Прошу:"),
        "generic/statement.docx": lambda: generic("ЗАЯВЛЕНИЕ", "{{ title }}", "Прошу:"),
        "generic/lawsuit.docx": lambda: generic("ИСКОВОЕ ЗАЯВЛЕНИЕ", "{{ title }}", "На основании изложенного прошу суд:"),
        "generic/appeal.docx": lambda: generic("АПЕЛЛЯЦИОННАЯ ЖАЛОБА", "{{ title }}", "Прошу:"),
        "generic/claim_letter.docx": claim_letter,
        "generic/motion.docx": lambda: generic("ХОДАТАЙСТВО", "{{ title }}{% if f.case_number %} (дело № {{ f.case_number }}){% endif %}", "Прошу:"),
    }
    only = set(sys.argv[1:])  # e.g. generic/claim_letter.docx — rebuild just these
    for rel, build in out.items():
        if only and rel not in only:
            continue
        path = ROOT / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        build().save(path)
        print("wrote", path)


if __name__ == "__main__":
    main()
