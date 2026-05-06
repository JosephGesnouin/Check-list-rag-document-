"""ReportLab PDF report + ZIP bundle helpers."""
from __future__ import annotations

import datetime as _dt
import io
import os
import zipfile
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


def _truncate(s: str, n: int = 240) -> str:
    s = (s or "").replace("\n", " ").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def _table_style(header_color: str = "#0d3b66") -> TableStyle:
    return TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(header_color)),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f7fa")]),
        ]
    )


def generate_pdf_report(result: DocumentAuditResult) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
        title=f"KM Audit - {result.file_name}",
    )
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], textColor=colors.HexColor("#0d3b66"))
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], textColor=colors.HexColor("#0d3b66"))
    body = styles["BodyText"]

    flow: List[Any] = [Paragraph("Rapport d'audit KM / IA-readiness", h1), Spacer(1, 0.3 * cm)]

    cartouche = [
        ["Fichier", result.file_name],
        ["Type", result.file_type.upper()],
        ["Taille", f"{result.file_size/1024:.1f} Ko"],
        ["Date d'audit", result.audit_date],
        ["Verdict", result.verdict],
        ["Score", f"{result.score}/100"],
    ]
    cart_table = Table(cartouche, colWidths=[4.5 * cm, 12 * cm])
    cart_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e3eaf1")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("BACKGROUND", (1, 4), (1, 4), _verdict_color(result.verdict)),
                ("TEXTCOLOR", (1, 4), (1, 4), colors.white),
                ("FONTNAME", (1, 4), (1, 4), "Helvetica-Bold"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    flow.extend([cart_table, Spacer(1, 0.5 * cm)])

    if result.parse_error:
        flow.append(Paragraph(f"<b>Avertissement parsing:</b> {result.parse_error}", body))
        flow.append(Spacer(1, 0.3 * cm))

    flow.append(Paragraph("Synthèse des non-conformités", h2))
    blockers = result.blocking_failures
    if blockers:
        rows = [["Règle", "Catégorie", "Sévérité", "Preuve / Recommandation"]]
        for r in blockers:
            rows.append(
                [
                    f"{r.rule_id} – {r.title}",
                    CATEGORIES.get(r.category, r.category),
                    r.severity.value,
                    Paragraph(
                        f"<b>{_truncate(r.evidence, 220)}</b><br/>{_truncate(r.recommendation, 220)}",
                        body,
                    ),
                ]
            )
        t = Table(rows, colWidths=[5 * cm, 3 * cm, 2 * cm, 7 * cm], repeatRows=1)
        t.setStyle(_table_style(header_color="#c62828"))
        flow.append(t)
    else:
        flow.append(Paragraph("Aucune non-conformité bloquante détectée.", body))
    flow.append(Spacer(1, 0.5 * cm))

    flow.append(Paragraph("Détail par catégorie", h2))
    for cat_code, cat_label in CATEGORIES.items():
        cat_rules = [r for r in result.rules if r.category == cat_code]
        if not cat_rules:
            continue
        flow.append(Paragraph(f"{cat_code} – {cat_label}", styles["Heading3"]))
        rows = [["Règle", "Statut", "Sévérité", "Preuve", "Recommandation"]]
        for r in cat_rules:
            rows.append(
                [
                    f"{r.rule_id} {r.title}",
                    r.status.value,
                    r.severity.value,
                    Paragraph(_truncate(r.evidence, 240), body),
                    Paragraph(_truncate(r.recommendation, 240), body),
                ]
            )
        t = Table(rows, colWidths=[4.5 * cm, 1.8 * cm, 1.6 * cm, 4.6 * cm, 4.5 * cm], repeatRows=1)
        t.setStyle(_table_style())
        for i, r in enumerate(cat_rules, start=1):
            t.setStyle(TableStyle([("TEXTCOLOR", (1, i), (1, i), _status_color(r.status))]))
        flow.append(KeepTogether(t))
        flow.append(Spacer(1, 0.3 * cm))

    flow.append(PageBreak())
    flow.append(Paragraph("Annexe – Métriques détectées", h2))
    metric_rows = [["Métrique", "Valeur"]] + [[k, str(v)] for k, v in result.metrics.items()]
    mt = Table(metric_rows, colWidths=[6 * cm, 6 * cm])
    mt.setStyle(_table_style())
    flow.append(mt)
    flow.append(Spacer(1, 0.4 * cm))
    flow.append(
        Paragraph(
            "Limites: certaines vérifications sont heuristiques (cartouche, légendes, "
            "alignement). Les règles marquées NOT_VERIFIABLE doivent être confirmées manuellement.",
            body,
        )
    )

    doc.build(flow)
    return buffer.getvalue()


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
