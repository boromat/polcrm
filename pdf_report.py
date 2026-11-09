"""PDF report generator for audits - fpdf2 with DejaVu Sans (Polish characters)."""

from pathlib import Path

from fpdf import FPDF

from i18n import _

FONTS_DIR = Path(__file__).parent / "static" / "fonts"
DEJAVU_REGULAR = FONTS_DIR / "DejaVuSans.ttf"
DEJAVU_BOLD = FONTS_DIR / "DejaVuSans-Bold.ttf"


def ensure_fonts():
    """DejaVu Sans (polskie znaki) leży w repozytorium, w static/fonts. Brak pliku = błąd instalacji."""
    missing = [p.name for p in (DEJAVU_REGULAR, DEJAVU_BOLD) if not p.is_file()]
    if missing:
        raise FileNotFoundError(
            f"Brak fontów {', '.join(missing)} w {FONTS_DIR} - przywróć je z repozytorium."
        )


def register_fonts(pdf):
    """Rejestruje DejaVu Sans jako 'dejavu' i 'dejavu-bold' w dokumencie fpdf2."""
    ensure_fonts()
    pdf.add_font("dejavu", "", str(DEJAVU_REGULAR))
    pdf.add_font("dejavu-bold", "", str(DEJAVU_BOLD))


def score_color(score):
    """Return RGB tuple for score value."""
    if not score:
        return (150, 150, 150)
    if score >= 4:
        return (16, 185, 129)  # emerald
    if score >= 3:
        return (245, 158, 11)  # amber
    return (239, 68, 68)  # red


def bar_width(score, max_w=50):
    """Width of score bar in mm."""
    if not score:
        return 0
    return max(2, int(score / 5 * max_w))


class AuditPDF(FPDF):
    def __init__(self, agency_name=""):
        super().__init__()
        self.agency_name = agency_name

    def header(self):
        if self.agency_name:
            self.set_font("dejavu", "", 7)
            self.set_text_color(150, 150, 150)
            self.cell(0, 5, self.agency_name, align="R")
            self.ln(6)

    def footer(self):
        self.set_y(-12)
        self.set_font("dejavu", "", 7)
        self.set_text_color(150, 150, 150)
        self.cell(0, 5, _("Strona %(page)s/{nb} | PolCRM", page=self.page_no()), align="C")

    def section_title(self, text):
        self.set_font("dejavu-bold", "", 11)
        self.set_text_color(108, 92, 231)
        self.cell(0, 8, text)
        self.ln(9)
        self.set_draw_color(108, 92, 231)
        self.set_line_width(0.3)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(3)

    def score_row(self, label, score, desc=""):
        self.set_font("dejavu", "", 9)
        self.set_text_color(60, 60, 60)
        self.cell(55, 6, label)
        # Bar
        x = self.get_x()
        y = self.get_y()
        self.set_fill_color(230, 230, 230)
        self.rect(x, y + 1, 50, 4, "F")
        r, g, b = score_color(score)
        self.set_fill_color(r, g, b)
        self.rect(x, y + 1, bar_width(score), 4, "F")
        self.set_x(x + 53)
        self.set_font("dejavu-bold", "", 9)
        self.set_text_color(r, g, b)
        self.cell(12, 6, f"{score}/5" if score else "-")
        if desc:
            self.set_font("dejavu", "", 7)
            self.set_text_color(150, 150, 150)
            self.cell(0, 6, desc)
        self.ln(7)


def generate_audit_pdf(audit, company, competitors, settings):
    """Generate a PDF report and return the file path."""
    agency_name = settings.agency_name if settings else ""
    pdf = AuditPDF(agency_name=agency_name)
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=15)

    register_fonts(pdf)

    pdf.add_page()

    # ── Title ─────────────────────────────────────────
    pdf.set_font("dejavu-bold", "", 18)
    pdf.set_text_color(30, 30, 50)
    pdf.cell(0, 10, _("Audyt marketingowy"), align="C")
    pdf.ln(12)

    pdf.set_font("dejavu-bold", "", 14)
    pdf.set_text_color(108, 92, 231)
    pdf.cell(0, 8, company.name, align="C")
    pdf.ln(10)

    # Company info line
    pdf.set_font("dejavu", "", 8)
    pdf.set_text_color(120, 120, 120)
    info_parts = [company.address]
    if company.phone:
        info_parts.append(company.phone)
    if company.industry:
        info_parts.append(company.industry)
    pdf.cell(0, 5, " | ".join(p for p in info_parts if p), align="C")
    pdf.ln(4)
    pdf.cell(0, 5, _("Data audytu: %(date)s", date=audit.created_at.strftime("%d.%m.%Y")), align="C")
    pdf.ln(10)

    # ── Overall Score ─────────────────────────────────
    pdf.set_font("dejavu", "", 9)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 5, _("OCENA OGÓLNA"), align="C")
    pdf.ln(6)
    r, g, b = score_color(audit.score_overall)
    pdf.set_font("dejavu-bold", "", 28)
    pdf.set_text_color(r, g, b)
    score_text = f"{audit.score_overall}/5" if audit.score_overall else "-"
    pdf.cell(0, 14, score_text, align="C")
    pdf.ln(16)

    # ── Scores breakdown ──────────────────────────────
    fn = "dejavu"
    fnb = "dejavu-bold"

    pdf.section_title(_("Scoring - 5 obszarów"))

    score_items = [
        (_("Widoczność online"), audit.score_visibility, _("Znajdowalność w internecie")),
        (_("Oferta i komunikacja"), audit.score_offer, _("Prezentacja oferty i dane kontaktowe")),
        (_("Zaufanie i dowód społeczny"), audit.score_trust, _("Opinie i reputacja online")),
        (_("Konwersja"), audit.score_conversion, _("Skuteczność strony www")),
        (_("Analityka i mierzenie"), audit.score_analytics, _("Mierzenie efektów działań")),
    ]
    for label, score, desc in score_items:
        pdf.score_row(label, score, desc)

    pdf.ln(4)

    # ── Problems / Opportunities / Recommendations ────
    problems = audit.top_problems or []
    opps = audit.top_opportunities or []
    recs = audit.recommended_actions or []

    if problems:
        pdf.section_title(_("Główne problemy"))
        pdf.set_font(fn, "", 9)
        pdf.set_text_color(60, 60, 60)
        for i, p in enumerate(problems, 1):
            pdf.cell(8, 6, f"{i}.")
            pdf.multi_cell(0, 6, p, new_x="LMARGIN", new_y="NEXT")

    if opps:
        pdf.ln(2)
        pdf.section_title(_("Największe szanse"))
        pdf.set_font(fn, "", 9)
        pdf.set_text_color(60, 60, 60)
        for i, o in enumerate(opps, 1):
            pdf.cell(8, 6, f"{i}.")
            pdf.multi_cell(0, 6, o, new_x="LMARGIN", new_y="NEXT")

    if recs:
        pdf.ln(2)
        pdf.section_title(_("Rekomendowane działania"))
        pdf.set_font(fn, "", 9)
        pdf.set_text_color(60, 60, 60)
        for i, r in enumerate(recs, 1):
            pdf.cell(8, 6, f"{i}.")
            pdf.multi_cell(0, 6, r, new_x="LMARGIN", new_y="NEXT")

    # ── PageSpeed ─────────────────────────────────────
    if audit.pagespeed_mobile or audit.pagespeed_desktop:
        pdf.ln(2)
        pdf.section_title("PageSpeed Insights")
        pdf.set_font(fn, "", 9)
        pdf.set_text_color(60, 60, 60)
        if audit.pagespeed_mobile:
            r, g, b = score_color(5 if audit.pagespeed_mobile >= 90 else (3 if audit.pagespeed_mobile >= 50 else 1))
            pdf.cell(30, 6, "Mobile:")
            pdf.set_font(fnb, "", 9)
            pdf.set_text_color(r, g, b)
            pdf.cell(20, 6, str(audit.pagespeed_mobile))
            pdf.set_text_color(60, 60, 60)
            pdf.set_font(fn, "", 9)
            pdf.cell(0, 6, "/ 100")
            pdf.ln(6)
        if audit.pagespeed_desktop:
            r, g, b = score_color(5 if audit.pagespeed_desktop >= 90 else (3 if audit.pagespeed_desktop >= 50 else 1))
            pdf.cell(30, 6, "Desktop:")
            pdf.set_font(fnb, "", 9)
            pdf.set_text_color(r, g, b)
            pdf.cell(20, 6, str(audit.pagespeed_desktop))
            pdf.set_text_color(60, 60, 60)
            pdf.set_font(fn, "", 9)
            pdf.cell(0, 6, "/ 100")
            pdf.ln(6)

    # ── Competitors ───────────────────────────────────
    if competitors:
        pdf.ln(2)
        pdf.section_title(_("Porównanie z konkurencją"))

        # Table header
        pdf.set_font(fnb, "", 8)
        pdf.set_text_color(100, 100, 100)
        col_w = [55, 20, 20, 20, 22, 22]
        headers = [_("Firma"), _("Ocena"), _("Opinii"), _("WWW"), _("Widoczn."), _("Zaufanie")]
        for i, h in enumerate(headers):
            pdf.cell(col_w[i], 6, h)
        pdf.ln(7)

        # Audited company row
        pdf.set_font(fnb, "", 8)
        pdf.set_text_color(108, 92, 231)
        name_display = company.name[:25] + "..." if len(company.name) > 25 else company.name
        pdf.cell(col_w[0], 5, _("%(name)s (Ty)", name=name_display))
        pdf.set_font(fn, "", 8)
        pdf.set_text_color(60, 60, 60)
        pdf.cell(col_w[1], 5, f"★ {company.rating}" if company.rating else "-")
        pdf.cell(col_w[2], 5, str(company.user_ratings_total or "-"))
        pdf.cell(col_w[3], 5, _("Tak") if company.website else _("Nie"))
        pdf.cell(col_w[4], 5, str(audit.score_visibility or "-"))
        pdf.cell(col_w[5], 5, str(audit.score_trust or "-"))
        pdf.ln(6)

        # Competitor rows
        for c in competitors:
            pdf.set_font(fn, "", 8)
            pdf.set_text_color(60, 60, 60)
            c_name = c.name[:25] + "..." if len(c.name) > 25 else c.name
            pdf.cell(col_w[0], 5, c_name)
            pdf.cell(col_w[1], 5, f"★ {c.rating}" if c.rating else "-")
            pdf.cell(col_w[2], 5, str(c.user_ratings_total or "-"))
            pdf.cell(col_w[3], 5, _("Tak") if c.website else _("Nie"))
            pdf.cell(col_w[4], 5, str(c.score_visibility or "-"))
            pdf.cell(col_w[5], 5, str(c.score_trust or "-"))
            pdf.ln(6)

    # ── Plan 90 ───────────────────────────────────────
    plan = audit.section_plan90 or {}
    actions = plan.get("actions", []) if isinstance(plan, dict) else []
    if actions:
        pdf.ln(2)
        pdf.section_title(_("Plan 90 dni"))
        pdf.set_font(fn, "", 9)
        pdf.set_text_color(60, 60, 60)
        for i, action in enumerate(actions, 1):
            pdf.set_font(fnb, "", 9)
            pdf.set_text_color(108, 92, 231)
            pdf.cell(8, 6, f"{i}.")
            pdf.set_font(fn, "", 9)
            pdf.set_text_color(60, 60, 60)
            pdf.multi_cell(0, 6, action, new_x="LMARGIN", new_y="NEXT")

    # ── Footer info ───────────────────────────────────
    pdf.ln(8)
    pdf.set_draw_color(200, 200, 200)
    pdf.set_line_width(0.2)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(3)
    pdf.set_font(fn, "", 7)
    pdf.set_text_color(150, 150, 150)
    footer_parts = []
    if settings and settings.agency_name:
        footer_parts.append(settings.agency_name)
    if settings and settings.agency_phone:
        footer_parts.append(settings.agency_phone)
    if settings and settings.agency_email:
        footer_parts.append(settings.agency_email)
    if footer_parts:
        pdf.cell(0, 4, " | ".join(footer_parts), align="C")
        pdf.ln(4)

    # Save
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)
    safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in company.name)
    pdf_path = output_dir / f"audyt_{safe_name}_{audit.id}.pdf"
    pdf.output(str(pdf_path))
    return str(pdf_path)
