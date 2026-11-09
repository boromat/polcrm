"""PDF generator for contracts - reuses DejaVu font from pdf_report.py."""

from pathlib import Path

from fpdf import FPDF

import i18n
from pdf_report import register_fonts


class ContractPDF(FPDF):
    def __init__(self, agency_name="", lang=None):
        super().__init__()
        self.agency_name = agency_name
        # The contract is a document for the client: its language, not the UI language
        self.lang = lang or i18n.DEFAULT_LANGUAGE

    def header(self):
        if self.agency_name and self.page_no() > 1:
            self.set_font("dejavu", "", 7)
            self.set_text_color(150, 150, 150)
            self.cell(0, 5, self.agency_name, align="R")
            self.ln(6)

    def footer(self):
        self.set_y(-12)
        self.set_font("dejavu", "", 7)
        self.set_text_color(150, 150, 150)
        self.cell(0, 5, i18n.gettext("Strona %(page)s/%(total)s", self.lang)
                  % {"page": self.page_no(), "total": "{nb}"}, align="C")


def generate_contract_pdf(title, rendered_text, output_path, agency_name="", lang=None):
    """Render plaintext rendered_text into a PDF at output_path (footer in ``lang``, default DEFAULT_LANGUAGE)."""
    pdf = ContractPDF(agency_name=agency_name, lang=lang)
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=20)

    register_fonts(pdf)
    main_font = "dejavu"
    bold_font = "dejavu-bold"

    pdf.add_page()

    # Title
    pdf.set_font(bold_font, "", 14)
    pdf.set_text_color(30, 30, 50)
    pdf.cell(0, 10, title, align="C")
    pdf.ln(12)

    # Body - split by newlines, render paragraphs
    pdf.set_font(main_font, "", 10)
    pdf.set_text_color(40, 40, 40)
    for line in rendered_text.split("\n"):
        line = line.rstrip()
        if not line:
            pdf.ln(4)
            continue
        # Heuristic: uppercase short lines = headings
        if line.isupper() and len(line) < 80:
            pdf.ln(2)
            pdf.set_font(bold_font, "", 11)
            pdf.set_text_color(108, 92, 231)
            pdf.multi_cell(0, 6, line, new_x="LMARGIN", new_y="NEXT")
            pdf.set_font(main_font, "", 10)
            pdf.set_text_color(40, 40, 40)
            pdf.ln(1)
        elif line.startswith("§"):
            pdf.ln(1)
            pdf.set_font(bold_font, "", 10)
            pdf.set_text_color(30, 30, 50)
            pdf.multi_cell(0, 6, line, new_x="LMARGIN", new_y="NEXT")
            pdf.set_font(main_font, "", 10)
            pdf.set_text_color(40, 40, 40)
        else:
            # Strip tabs
            line = line.replace("\t", "    ")
            pdf.multi_cell(0, 5.5, line, new_x="LMARGIN", new_y="NEXT")

    # Save
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(output_path))
    return str(output_path)
