"""ReportLab PDF report + ZIP bundle helpers."""
from __future__ import annotations

import datetime as _dt
import io
import os
import zipfile
from html import escape
from typing import Any, List, Tuple

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .config import CATEGORIES
from .models import DocumentAuditResult, Status


# ---------------------------------------------------------------------------
# Page geometry
# ---------------------------------------------------------------------------

PAGE_MARGIN = 1.5 * cm
USABLE_WIDTH = A4[0] - 2 * PAGE_MARGIN  # 18 cm

# 5-column layout for the per-category rule tables, fits USABLE_WIDTH.
# Severity uses 3-letter codes (BLOC/MAJ/MIN) so the column stays narrow
# and the rule title gets more horizontal room.
COL_RULE = 6.4 * cm
COL_STATUS = 1.2 * cm
COL_SEVERITY = 1.2 * cm
COL_EVIDENCE = 4.6 * cm
COL_RECO = USABLE_WIDTH - COL_RULE - COL_STATUS - COL_SEVERITY - COL_EVIDENCE


# ---------------------------------------------------------------------------
# Status/verdict color helpers
# ---------------------------------------------------------------------------

_STATUS_LABEL = {
    Status.PASS: "PASS",
    Status.FAIL: "FAIL",
    Status.WARN: "WARN",
    Status.NOT_VERIFIABLE: "N/V",
}

_SEVERITY_LABEL = {"BLOCKER": "BLOC", "MAJOR": "MAJ", "MINOR": "MIN"}


def _verdict_color(verdict: str):
    return {
        "Feu Vert": colors.HexColor("#2e7d32"),
        "Feu Orange": colors.HexColor("#ef6c00"),
        "Feu Rouge": colors.HexColor("#c62828"),
    }.get(verdict, colors.grey)


def _status_color(status: Status):
    return {
        Status.PASS: colors.HexColor("#2e7d32"),
        Status.FAIL: colors.HexColor("#c62828"),
        Status.WARN: colors.HexColor("#ef6c00"),
        Status.NOT_VERIFIABLE: colors.HexColor("#616161"),
    }.get(status, colors.black)


# ---------------------------------------------------------------------------
# Paragraph styles for table cells (auto-wrap, small font, break long tokens)
# ---------------------------------------------------------------------------

_BASE_STYLES = getSampleStyleSheet()


def _cell_style(name: str, **overrides) -> ParagraphStyle:
    base = ParagraphStyle(
        name,
        parent=_BASE_STYLES["BodyText"],
        fontName="Helvetica",
        fontSize=8,
        leading=10,
        wordWrap="CJK",  # allows breaking long tokens (URLs, IBANs, …)
        spaceBefore=0,
        spaceAfter=0,
    )
    for k, v in overrides.items():
        setattr(base, k, v)
    return base


_CELL = _cell_style("CellText")
_CELL_BOLD = _cell_style("CellBold", fontName="Helvetica-Bold")
_CELL_HEADER = _cell_style(
    "CellHeader", fontName="Helvetica-Bold", textColor=colors.white
)
_CELL_STATUS_BASE = _cell_style("CellStatus", alignment=1, fontName="Helvetica-Bold")


def _cell(text: str, style: ParagraphStyle = _CELL) -> Paragraph:
    """Plain-text cell. Escapes HTML-significant chars so the source
    text is rendered verbatim (no surprise interpretation of ``<`` or
    ``&``)."""
    return Paragraph(escape(text or "—"), style)


def _cell_html(html: str, style: ParagraphStyle = _CELL) -> Paragraph:
    """HTML-aware cell. Caller is responsible for escaping any
    user-provided text inside the markup."""
    return Paragraph(html or "—", style)


def _status_cell(status: Status) -> Paragraph:
    style = _cell_style(
        f"CellStatus_{status.value}",
        alignment=1,
        fontName="Helvetica-Bold",
        textColor=_status_color(status),
    )
    return Paragraph(_STATUS_LABEL[status], style)


def _table_style(header_color: str = "#0d3b66") -> TableStyle:
    return TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(header_color)),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f7fa")]),
        ]
    )


# ---------------------------------------------------------------------------
# PDF report
# ---------------------------------------------------------------------------


def generate_pdf_report(result: DocumentAuditResult) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=PAGE_MARGIN,
        rightMargin=PAGE_MARGIN,
        topMargin=PAGE_MARGIN,
        bottomMargin=PAGE_MARGIN,
        title=f"KM Audit - {result.file_name}",
    )
    styles = _BASE_STYLES
    h1 = ParagraphStyle("h1", parent=styles["Heading1"],
                        textColor=colors.HexColor("#0d3b66"), spaceAfter=8)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"],
                        textColor=colors.HexColor("#0d3b66"), spaceAfter=6)
    h3 = ParagraphStyle("h3", parent=styles["Heading3"], spaceAfter=4)

    flow: List[Any] = [
        Paragraph("Rapport d'audit KM / IA-readiness", h1),
        Spacer(1, 0.2 * cm),
    ]

    # ---- Cartouche -------------------------------------------------------
    cart_label = _cell_style("CartLabel", fontName="Helvetica-Bold")
    cart_value = _cell_style("CartValue")
    cart_value_strong = _cell_style(
        "CartValueStrong", fontName="Helvetica-Bold", textColor=colors.white
    )
    cartouche_rows = [
        [_cell("Fichier", cart_label), _cell(result.file_name, cart_value)],
        [_cell("Type", cart_label), _cell(result.file_type.upper(), cart_value)],
        [_cell("Taille", cart_label), _cell(f"{result.file_size/1024:.1f} Ko", cart_value)],
        [_cell("Date d'audit", cart_label), _cell(result.audit_date, cart_value)],
        [_cell("Verdict", cart_label), _cell(result.verdict, cart_value_strong)],
        [_cell("Score", cart_label), _cell(f"{result.score}/100", cart_value)],
    ]
    cart_table = Table(
        cartouche_rows,
        colWidths=[4.5 * cm, USABLE_WIDTH - 4.5 * cm],
    )
    cart_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e3eaf1")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("BACKGROUND", (1, 4), (1, 4), _verdict_color(result.verdict)),
            ]
        )
    )
    flow.extend([cart_table, Spacer(1, 0.5 * cm)])

    if result.parse_error:
        flow.append(Paragraph(f"<b>Avertissement parsing :</b> {escape(result.parse_error)}",
                              styles["BodyText"]))
        flow.append(Spacer(1, 0.3 * cm))

    # ---- Synthèse des bloquants -----------------------------------------
    flow.append(Paragraph("Synthèse des non-conformités", h2))
    blockers = result.blocking_failures
    if blockers:
        rows = [[
            _cell("Règle", _CELL_HEADER),
            _cell("Catégorie", _CELL_HEADER),
            _cell("Sévérité", _CELL_HEADER),
            _cell("Preuve / Recommandation", _CELL_HEADER),
        ]]
        for r in blockers:
            evidence_html = (
                f"<b>{escape(r.evidence) or '—'}</b><br/>{escape(r.recommendation) or ''}"
            )
            rows.append([
                _cell(f"{r.rule_id} – {r.title}"),
                _cell(CATEGORIES.get(r.category, r.category)),
                _cell(r.severity.value),
                _cell_html(evidence_html, _CELL),
            ])
        synth_widths = [
            5.0 * cm, 4.5 * cm, 1.8 * cm,
            USABLE_WIDTH - 5.0 * cm - 4.5 * cm - 1.8 * cm,
        ]
        t = Table(rows, colWidths=synth_widths, repeatRows=1)
        t.setStyle(_table_style(header_color="#c62828"))
        flow.append(t)
    else:
        flow.append(Paragraph("Aucune non-conformité bloquante détectée.",
                              styles["BodyText"]))
    flow.append(Spacer(1, 0.5 * cm))

    # ---- Détail par catégorie -------------------------------------------
    flow.append(Paragraph("Détail par catégorie", h2))
    for cat_code, cat_label in CATEGORIES.items():
        cat_rules = [r for r in result.rules if r.category == cat_code]
        if not cat_rules:
            continue
        flow.append(Paragraph(f"{cat_code} – {cat_label}", h3))
        rows = [[
            _cell("Règle", _CELL_HEADER),
            _cell("Statut", _CELL_HEADER),
            _cell("Sévérité", _CELL_HEADER),
            _cell("Preuve", _CELL_HEADER),
            _cell("Recommandation", _CELL_HEADER),
        ]]
        for r in cat_rules:
            rows.append([
                _cell_html(
                    f"<b>{escape(r.rule_id)}</b> {escape(r.title)}",
                    _CELL,
                ),
                _status_cell(r.status),
                _cell(_SEVERITY_LABEL.get(r.severity.value, r.severity.value)),
                _cell(r.evidence),
                _cell(r.recommendation),
            ])
        t = Table(
            rows,
            colWidths=[COL_RULE, COL_STATUS, COL_SEVERITY, COL_EVIDENCE, COL_RECO],
            repeatRows=1,
        )
        t.setStyle(_table_style())
        flow.append(t)
        flow.append(Spacer(1, 0.3 * cm))

    # ---- Annexe : métriques ---------------------------------------------
    flow.append(PageBreak())
    flow.append(Paragraph("Annexe – Métriques détectées", h2))
    metric_rows = [[_cell("Métrique", _CELL_HEADER), _cell("Valeur", _CELL_HEADER)]] + [
        [_cell(str(k)), _cell(str(v))] for k, v in result.metrics.items()
    ]
    mt = Table(metric_rows, colWidths=[8 * cm, USABLE_WIDTH - 8 * cm])
    mt.setStyle(_table_style())
    flow.append(mt)
    flow.append(Spacer(1, 0.4 * cm))
    flow.append(
        Paragraph(
            "Limites: certaines vérifications sont heuristiques (cartouche, légendes, "
            "alignement). Les règles marquées N/V doivent être confirmées manuellement.",
            styles["BodyText"],
        )
    )

    doc.build(flow, onFirstPage=_footer, onLaterPages=_footer)
    return buffer.getvalue()


def _footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.grey)
    canvas.drawString(PAGE_MARGIN, 0.8 * cm, "KM Audit – rapport offline")
    canvas.drawRightString(
        A4[0] - PAGE_MARGIN, 0.8 * cm, f"Page {doc.page}"
    )
    canvas.restoreState()


# ---------------------------------------------------------------------------
# File naming and bundle
# ---------------------------------------------------------------------------


def pdf_filename(source_name: str) -> str:
    base = os.path.splitext(os.path.basename(source_name))[0]
    today = _dt.date.today().strftime("%Y%m%d")
    return f"{base}__KM_AUDIT__{today}.pdf"


def generate_zip(reports: List[Tuple[str, bytes]]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in reports:
            zf.writestr(name, data)
    return buf.getvalue()
