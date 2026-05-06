"""KM Document Audit - Streamlit app for offline KM/AI-readiness quality gates.

Audits DOCX/PPTX/XLSX/PDF documents against a configurable checklist
(naming, cartouche, structure, images, tables, diagrams, URLs, sensitive
data, best practices), scores them, and produces a per-document PDF
report (ReportLab) plus an optional ZIP bundle.

Runs fully offline. No network, no external API. All heuristics are
explicit and limitations are flagged as NOT_VERIFIABLE when relevant.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import io
import os
import re
import sys
import zipfile
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st

# ---------------------------------------------------------------------------
# Optional document parsers (kept optional so the app degrades gracefully).
# ---------------------------------------------------------------------------
try:
    from docx import Document as DocxDocument
    from docx.oxml.ns import qn as _docx_qn
except Exception:  # pragma: no cover
    DocxDocument = None
    _docx_qn = None

try:
    from pptx import Presentation
    from pptx.enum.shapes import MSO_SHAPE_TYPE
except Exception:  # pragma: no cover
    Presentation = None
    MSO_SHAPE_TYPE = None

try:
    import openpyxl
    from openpyxl.utils import get_column_letter  # noqa: F401
except Exception:  # pragma: no cover
    openpyxl = None

try:
    from PyPDF2 import PdfReader
except Exception:  # pragma: no cover
    PdfReader = None

try:
    from PIL import Image, ImageFilter
    import numpy as np
except Exception:  # pragma: no cover
    Image = None
    ImageFilter = None
    np = None

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


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

PASS, FAIL, WARN, NV = "PASS", "FAIL", "WARN", "NOT_VERIFIABLE"
BLOCKER, MAJOR, MINOR = "BLOCKER", "MAJOR", "MINOR"

CATEGORIES = {
    "A": "Identification",
    "B": "Structure",
    "C": "Images",
    "D": "Tableaux",
    "E": "Diagrammes",
    "F": "URLs",
    "G": "Bonnes pratiques",
    "H": "Données sensibles",
}


@dataclass
class RuleResult:
    rule_id: str
    category: str
    title: str
    status: str
    severity: str
    evidence: str = ""
    location: str = ""
    recommendation: str = ""

    def is_blocker_fail(self) -> bool:
        return self.severity == BLOCKER and self.status == FAIL


@dataclass
class DocumentAuditResult:
    file_name: str
    file_type: str
    file_size: int
    audit_date: str
    rules: List[RuleResult] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    score: float = 0.0
    verdict: str = "Feu Rouge"
    parse_error: Optional[str] = None

    @property
    def blocking_failures(self) -> List[RuleResult]:
        return [r for r in self.rules if r.is_blocker_fail()]


# ---------------------------------------------------------------------------
# Default thresholds (overridable via UI)
# ---------------------------------------------------------------------------
DEFAULT_SETTINGS = {
    "max_paragraph_chars": 600,
    "max_avg_sentence_words": 25,
    "min_image_width": 500,
    "min_image_height": 350,
    "blur_variance_threshold": 80.0,
    "long_doc_pages": 10,
    "min_headings_per_pages": 0.5,  # at least 1 heading per 2 pages
    "score_pass_threshold": 80,
    "weight_blocking": 70,
    "weight_practices": 30,
}

NAMING_REGEX = re.compile(
    r"^(?P<date>\d{8})_(?P<subject>[^_]+)_(?P<doctype>[^_]+)(?:_(?P<extra>.+))?\."
    r"(?P<ext>docx|pptx|pdf|xlsx)$",
    re.IGNORECASE,
)

REQUIRED_CARTOUCHE_FIELDS = [
    "Auteur",
    "Email",
    "Equipe",
    "Thème",
    "Type de document",
    "Description",
    "Mot",  # mot(s) clé(s)
    "Périmètre",
    "Entité",
    "Date d'échéance",
]

OBJECTIVE_HINTS = ("objectif", "objective", "description", "but ", "purpose")
GLOSSARY_HINTS = ("glossaire", "glossary", "acronymes", "acronyms", "définitions")

EMOJI_OR_SYMBOL_RE = re.compile(
    "["
    "←-⇿"   # arrows
    "☀-➿"   # misc symbols / dingbats (✓, ✗, etc.)
    "\U0001F300-\U0001FAFF"
    "]"
)
URL_RE = re.compile(r"https?://[^\s\)\]\>]+", re.IGNORECASE)
ACRONYM_RE = re.compile(r"\b([A-Z]{2,10})s?\b")

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE_RE = re.compile(
    r"(?:(?<!\d)(?:\+\d{1,3}[\s.\-]?)?(?:\(?\d{2,4}\)?[\s.\-]?){2,5}\d{2,4}(?!\d))"
)
IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){3,7}\b")
POSTAL_ADDR_RE = re.compile(
    r"\b\d{1,4}\s+(?:rue|avenue|av\.|bd|boulevard|place|chemin|impasse|allée|route|street|st\.|road|rd\.)\b",
    re.IGNORECASE,
)
CLIENT_ID_RE = re.compile(r"\b(?:client|customer|account|compte)[\s#:_-]*\d{4,}\b", re.IGNORECASE)

TRACKING_PARAMS = ("utm_", "gclid", "fbclid", "session", "sessionid", "token", "auth", "tracking")


# ---------------------------------------------------------------------------
# Loaders / extractors
# ---------------------------------------------------------------------------


@dataclass
class ParsedDoc:
    file_name: str
    file_type: str
    raw_bytes: bytes

    text_blocks: List[str] = field(default_factory=list)
    headings: List[Tuple[int, str]] = field(default_factory=list)  # (level, text)
    tables: List[Dict[str, Any]] = field(default_factory=list)
    images: List[Dict[str, Any]] = field(default_factory=list)
    urls: List[str] = field(default_factory=list)
    hyperlinks: List[Tuple[str, str]] = field(default_factory=list)  # (display, target)
    pages: int = 0
    extra: Dict[str, Any] = field(default_factory=dict)
    parse_warning: Optional[str] = None


def _ext(name: str) -> str:
    return os.path.splitext(name)[1].lower().lstrip(".")


def parse_document(file_name: str, raw: bytes) -> ParsedDoc:
    ext = _ext(file_name)
    parsed = ParsedDoc(file_name=file_name, file_type=ext, raw_bytes=raw)
    try:
        if ext == "docx":
            _parse_docx(parsed)
        elif ext == "pptx":
            _parse_pptx(parsed)
        elif ext == "xlsx":
            _parse_xlsx(parsed)
        elif ext == "pdf":
            _parse_pdf(parsed)
        else:
            parsed.parse_warning = f"Format non supporté: .{ext}"
    except Exception as exc:  # pragma: no cover - defensive
        parsed.parse_warning = f"Erreur de parsing: {exc}"
    return parsed


def _parse_docx(p: ParsedDoc) -> None:
    if DocxDocument is None:
        p.parse_warning = "python-docx non installé"
        return
    doc = DocxDocument(io.BytesIO(p.raw_bytes))
    body_paragraphs: List[str] = []
    for para in doc.paragraphs:
        text = (para.text or "").strip()
        if not text:
            continue
        body_paragraphs.append(text)
        style = (para.style.name or "") if para.style else ""
        m = re.match(r"Heading\s+(\d)", style)
        if m:
            p.headings.append((int(m.group(1)), text))
    p.text_blocks.extend(body_paragraphs)

    for tbl in doc.tables:
        rows = []
        merged = False
        for row in tbl.rows:
            row_cells = []
            for cell in row.cells:
                row_cells.append(cell.text.strip())
                if _docx_qn is not None:
                    tcPr = cell._tc.find(_docx_qn("w:tcPr"))
                    if tcPr is not None and (
                        tcPr.find(_docx_qn("w:gridSpan")) is not None
                        or tcPr.find(_docx_qn("w:vMerge")) is not None
                    ):
                        merged = True
            rows.append(row_cells)
        first_row_bold = False
        try:
            first_row_bold = all(
                any(run.bold for run in para.runs)
                for cell in tbl.rows[0].cells
                for para in cell.paragraphs
                if para.runs
            )
        except Exception:
            first_row_bold = False
        p.tables.append(
            {"rows": rows, "merged": merged, "header_bold": first_row_bold, "source": "native"}
        )

    # Hyperlinks
    rels = doc.part.rels
    for rel in rels.values():
        if rel.reltype.endswith("/hyperlink"):
            target = rel.target_ref or ""
            if target.startswith("http"):
                p.urls.append(target)
                p.hyperlinks.append((target, target))

    try:
        for shape in doc.inline_shapes:
            p.images.append({"width": int(shape.width or 0), "height": int(shape.height or 0)})
    except Exception:
        pass

    p.pages = max(1, len(body_paragraphs) // 25)
    p.extra["has_headers_footers"] = any(
        sec.header.paragraphs and any(par.text.strip() for par in sec.header.paragraphs)
        for sec in doc.sections
    )


def _parse_pptx(p: ParsedDoc) -> None:
    if Presentation is None:
        p.parse_warning = "python-pptx non installé"
        return
    prs = Presentation(io.BytesIO(p.raw_bytes))
    standalone_textboxes = 0
    diagram_shape_counts: List[int] = []
    for idx, slide in enumerate(prs.slides, start=1):
        slide_text: List[str] = []
        title = ""
        if slide.shapes.title and slide.shapes.title.has_text_frame:
            title = (slide.shapes.title.text or "").strip()
            if title:
                p.headings.append((1, title))
                slide_text.append(title)
        shape_count = 0
        for shape in slide.shapes:
            shape_count += 1
            if shape.has_text_frame:
                txt = (shape.text_frame.text or "").strip()
                if txt:
                    slide_text.append(txt)
                    if shape != slide.shapes.title and not title:
                        # textbox without slide title context
                        standalone_textboxes += 1
            if shape.shape_type == 13 and Image is not None:  # picture
                try:
                    image = shape.image
                    img = Image.open(io.BytesIO(image.blob))
                    p.images.append(
                        {
                            "width": img.width,
                            "height": img.height,
                            "blur": _laplacian_variance(img),
                            "slide": idx,
                        }
                    )
                except Exception:
                    p.images.append({"width": 0, "height": 0, "slide": idx})
            if shape.has_table:
                tbl = shape.table
                rows = []
                merged = False
                for r in tbl.rows:
                    rows.append([c.text.strip() for c in r.cells])
                # python-pptx exposes spans on cells
                for r in tbl.rows:
                    for c in r.cells:
                        if getattr(c, "is_merge_origin", False) or getattr(
                            c, "is_spanned", False
                        ):
                            merged = True
                p.tables.append({"rows": rows, "merged": merged, "source": "native", "slide": idx})
        diagram_shape_counts.append(shape_count)
        p.text_blocks.append("\n".join(slide_text))

    for url in URL_RE.findall("\n".join(p.text_blocks)):
        p.urls.append(url)

    p.pages = len(prs.slides)
    p.extra["standalone_textboxes"] = standalone_textboxes
    p.extra["diagram_shape_counts"] = diagram_shape_counts


def _parse_xlsx(p: ParsedDoc) -> None:
    if openpyxl is None:
        p.parse_warning = "openpyxl non installé"
        return
    wb = openpyxl.load_workbook(io.BytesIO(p.raw_bytes), data_only=True)
    metadata_props = wb.properties
    p.extra["xlsx_props"] = {
        "title": metadata_props.title,
        "creator": metadata_props.creator,
        "subject": metadata_props.subject,
        "description": metadata_props.description,
        "keywords": metadata_props.keywords,
    }

    for ws in wb.worksheets:
        rows: List[List[str]] = []
        for row in ws.iter_rows(values_only=True):
            rows.append([str(c).strip() if c is not None else "" for c in row])
        merged = bool(ws.merged_cells.ranges)
        first_row_bold = False
        try:
            first_row_bold = any(
                (cell.font and cell.font.bold) for cell in next(ws.iter_rows(min_row=1, max_row=1))
            )
        except StopIteration:
            first_row_bold = False
        has_borders = False
        try:
            for row in ws.iter_rows(max_row=min(20, ws.max_row or 1)):
                for cell in row:
                    if cell.border and any(
                        getattr(getattr(cell.border, side, None), "style", None)
                        for side in ("left", "right", "top", "bottom")
                    ):
                        has_borders = True
                        break
                if has_borders:
                    break
        except Exception:
            pass
        p.tables.append(
            {
                "rows": rows,
                "merged": merged,
                "header_bold": first_row_bold,
                "borders": has_borders,
                "sheet": ws.title,
                "source": "native",
            }
        )
        p.text_blocks.append("\n".join("\t".join(r) for r in rows))

    p.pages = len(wb.worksheets)


def _parse_pdf(p: ParsedDoc) -> None:
    if PdfReader is None:
        p.parse_warning = "PyPDF2 non installé"
        return
    reader = PdfReader(io.BytesIO(p.raw_bytes))
    pages_text: List[str] = []
    for page in reader.pages:
        try:
            pages_text.append(page.extract_text() or "")
        except Exception:
            pages_text.append("")
    p.text_blocks = pages_text
    full = "\n".join(pages_text)
    if not full.strip():
        p.parse_warning = "Texte non extractible (PDF scanné ?). OCR non pris en charge."
    p.pages = len(reader.pages)
    # Heuristic headings: short uppercase lines or numbered prefixes
    for line in full.splitlines():
        s = line.strip()
        if 2 < len(s) < 80 and (
            re.match(r"^\d+(\.\d+)*\s+\S", s)
            or (s.upper() == s and len(s.split()) <= 8 and any(c.isalpha() for c in s))
        ):
            p.headings.append((1 if not re.match(r"^\d+\.\d", s) else 2, s))
    p.urls = URL_RE.findall(full)


def _laplacian_variance(img) -> float:
    """Approximate sharpness via variance of a Laplacian-filtered image."""
    if Image is None or np is None:
        return -1.0
    try:
        gray = img.convert("L")
        kernel = ImageFilter.Kernel(
            (3, 3), [0, 1, 0, 1, -4, 1, 0, 1, 0], scale=1, offset=0
        )
        filtered = gray.filter(kernel)
        arr = np.asarray(filtered, dtype=np.float32)
        return float(arr.var())
    except Exception:
        return -1.0


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------


def _truncate(s: str, n: int = 160) -> str:
    s = (s or "").replace("\n", " ").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def _full_text(p: ParsedDoc) -> str:
    return "\n".join(p.text_blocks)


def rule_naming(p: ParsedDoc) -> RuleResult:
    m = NAMING_REGEX.match(p.file_name)
    if m:
        return RuleResult(
            "A1",
            "A",
            "Nommage du fichier (AAAAMMJJ_Sujet_Type_Extra.ext)",
            PASS,
            BLOCKER,
            evidence=p.file_name,
        )
    return RuleResult(
        "A1",
        "A",
        "Nommage du fichier (AAAAMMJJ_Sujet_Type_Extra.ext)",
        FAIL,
        BLOCKER,
        evidence=p.file_name,
        recommendation="Renommer au format AAAAMMJJ_Sujet_TypeDeDocument(_Infos).ext, "
        "ex: 20260121_Guidelines_KM_Cash.pptx",
    )


def rule_cartouche(p: ParsedDoc) -> RuleResult:
    text = _full_text(p)
    head = text[:4000]  # focus on first portion
    found = []
    missing = []
    for label in REQUIRED_CARTOUCHE_FIELDS:
        if re.search(rf"\b{re.escape(label)}", head, re.IGNORECASE):
            found.append(label)
        else:
            missing.append(label)
    # XLSX metadata fallback
    props = p.extra.get("xlsx_props") if p.file_type == "xlsx" else None
    if props:
        if props.get("creator"):
            if "Auteur" in missing:
                missing.remove("Auteur")
                found.append("Auteur (xlsx props)")
        if props.get("keywords") and "Mot" in missing:
            missing.remove("Mot")
            found.append("Mots clés (xlsx props)")

    if len(missing) == 0:
        return RuleResult(
            "A2",
            "A",
            "Cartouche renseigné (champs obligatoires)",
            PASS,
            BLOCKER,
            evidence=", ".join(found),
        )
    if len(found) >= 4:
        return RuleResult(
            "A2",
            "A",
            "Cartouche renseigné (champs obligatoires)",
            FAIL,
            BLOCKER,
            evidence=f"Détectés: {', '.join(found)} | Manquants: {', '.join(missing)}",
            recommendation="Ajouter les champs manquants dans la section Cartouche.",
        )
    return RuleResult(
        "A2",
        "A",
        "Cartouche renseigné (champs obligatoires)",
        NV,
        BLOCKER,
        evidence="Cartouche non détecté automatiquement.",
        recommendation="Vérifier manuellement la présence d'un cartouche conforme.",
    )


def rule_objective(p: ParsedDoc) -> RuleResult:
    head = _full_text(p)[:3000].lower()
    if any(h in head for h in OBJECTIVE_HINTS):
        return RuleResult(
            "A3",
            "A",
            "Objectif/description en début de document",
            PASS,
            BLOCKER,
            evidence="Section objectif/description détectée",
        )
    return RuleResult(
        "A3",
        "A",
        "Objectif/description en début de document",
        FAIL,
        BLOCKER,
        recommendation="Ajouter une section Objectif/Description dans les premières pages.",
    )


def rule_acronyms(p: ParsedDoc) -> RuleResult:
    text = _full_text(p)
    acronyms = {a for a in ACRONYM_RE.findall(text) if a not in {"PDF", "DOCX", "PPTX", "XLSX"}}
    if not acronyms:
        return RuleResult("A4", "A", "Acronymes développés à la 1re occurrence", PASS, BLOCKER,
                          evidence="Aucun acronyme détecté")
    undocumented = []
    for ac in acronyms:
        # look for ACR (Definition) or ACR : Definition near first occurrence
        first = re.search(rf"\b{re.escape(ac)}\b", text)
        if not first:
            continue
        window = text[max(0, first.start() - 80): first.start() + 200]
        if not (
            re.search(rf"{ac}\s*\(([^)]+)\)", window)
            or re.search(rf"{ac}\s*[:\-–]\s*[A-Za-zÀ-ÿ]", window)
        ):
            undocumented.append(ac)
    if not undocumented:
        return RuleResult(
            "A4",
            "A",
            "Acronymes développés à la 1re occurrence",
            PASS,
            BLOCKER,
            evidence=f"{len(acronyms)} acronymes détectés, tous documentés",
        )
    return RuleResult(
        "A4",
        "A",
        "Acronymes développés à la 1re occurrence",
        FAIL,
        BLOCKER,
        evidence=f"Non développés: {', '.join(sorted(undocumented)[:15])}",
        recommendation="Développer chaque acronyme à sa première occurrence: ACR (Définition).",
    )


def rule_glossary(p: ParsedDoc) -> RuleResult:
    text = _full_text(p).lower()
    if any(h in text for h in GLOSSARY_HINTS):
        return RuleResult(
            "A5", "A", "Glossaire / liste d'acronymes présent", PASS, BLOCKER,
            evidence="Section glossaire/acronymes détectée",
        )
    return RuleResult(
        "A5", "A", "Glossaire / liste d'acronymes présent", FAIL, BLOCKER,
        recommendation="Ajouter une section Glossaire en fin de document.",
    )


def rule_headings_hierarchy(p: ParsedDoc) -> RuleResult:
    if not p.headings:
        return RuleResult(
            "B6", "B", "Titres descriptifs et hiérarchisés", FAIL, BLOCKER,
            recommendation="Utiliser les styles Heading/Titre de slide pour structurer le contenu.",
        )
    levels = sorted({lvl for lvl, _ in p.headings})
    multi_level = len(levels) >= 2 or p.file_type == "pptx"
    has_descriptive = all(2 <= len(t.split()) <= 18 for _, t in p.headings)
    if multi_level and has_descriptive:
        return RuleResult(
            "B6", "B", "Titres descriptifs et hiérarchisés", PASS, BLOCKER,
            evidence=f"{len(p.headings)} titres, niveaux={levels}",
        )
    return RuleResult(
        "B6", "B", "Titres descriptifs et hiérarchisés", WARN, BLOCKER,
        evidence=f"{len(p.headings)} titres, niveaux={levels}",
        recommendation="Vérifier la hiérarchie (H1/H2/H3) et le caractère descriptif des titres.",
    )


def rule_headings_density(p: ParsedDoc, settings: Dict[str, Any]) -> RuleResult:
    pages = max(1, p.pages)
    ratio = len(p.headings) / pages
    if ratio >= settings["min_headings_per_pages"]:
        return RuleResult(
            "B7", "B", "Densité de titres suffisante", PASS, BLOCKER,
            evidence=f"{len(p.headings)} titres / {pages} pages (ratio={ratio:.2f})",
        )
    return RuleResult(
        "B7", "B", "Densité de titres suffisante", FAIL, BLOCKER,
        evidence=f"{len(p.headings)} titres / {pages} pages (ratio={ratio:.2f})",
        recommendation="Ajouter des titres/sous-titres (au moins 1 toutes les 1-2 pages).",
    )


def rule_textboxes(p: ParsedDoc) -> RuleResult:
    if p.file_type == "pptx":
        n = p.extra.get("standalone_textboxes", 0)
        if n <= 2:
            return RuleResult("B8", "B", "Pas de boîtes/cadres inutiles", PASS, BLOCKER,
                              evidence=f"{n} textbox(es) hors titre")
        return RuleResult(
            "B8", "B", "Pas de boîtes/cadres inutiles", FAIL, BLOCKER,
            evidence=f"{n} textbox(es) hors titre détectés",
            recommendation="Limiter les zones de texte flottantes; privilégier le contenu dans les placeholders.",
        )
    return RuleResult(
        "B8", "B", "Pas de boîtes/cadres inutiles", NV, MAJOR,
        evidence="Détection automatique limitée hors PPTX",
    )


def rule_no_symbols_in_sentences(p: ParsedDoc) -> RuleResult:
    offenders = []
    for block in p.text_blocks:
        for line in block.splitlines():
            if EMOJI_OR_SYMBOL_RE.search(line) and len(line.split()) >= 4:
                offenders.append(_truncate(line, 120))
                if len(offenders) >= 5:
                    break
        if len(offenders) >= 5:
            break
    if not offenders:
        return RuleResult("B9", "B", "Pas de symboles/icônes dans les phrases", PASS, BLOCKER)
    return RuleResult(
        "B9", "B", "Pas de symboles/icônes dans les phrases", FAIL, BLOCKER,
        evidence=" | ".join(offenders),
        recommendation="Remplacer les symboles (✓, ➜, etc.) par des mots équivalents.",
    )


def rule_image_legends(p: ParsedDoc) -> RuleResult:
    if not p.images:
        return RuleResult("C10", "C", "Légende sous chaque image informative", PASS, MAJOR,
                          evidence="Aucune image détectée")
    text = _full_text(p).lower()
    hint = sum(text.count(h) for h in ("figure", "schéma", "schema", "illustration", "capture"))
    if hint >= len(p.images):
        return RuleResult("C10", "C", "Légende sous chaque image informative", PASS, BLOCKER,
                          evidence=f"{hint} mentions de légendes / {len(p.images)} images")
    if hint > 0:
        return RuleResult(
            "C10", "C", "Légende sous chaque image informative", WARN, BLOCKER,
            evidence=f"{hint} mentions de légendes / {len(p.images)} images",
            recommendation="Ajouter une légende explicite (Figure X – ...) sous chaque image informative.",
        )
    return RuleResult(
        "C10", "C", "Légende sous chaque image informative", FAIL, BLOCKER,
        evidence=f"{len(p.images)} images sans mention 'Figure/Schéma/...'",
        recommendation="Ajouter une légende (Figure X – ...) sous chaque image informative.",
    )


def rule_image_quality(p: ParsedDoc, settings: Dict[str, Any]) -> RuleResult:
    if not p.images:
        return RuleResult("C11", "C", "Qualité des images (résolution, netteté)", PASS, MAJOR,
                          evidence="Aucune image")
    bad = []
    for img in p.images:
        w = img.get("width", 0) or 0
        h = img.get("height", 0) or 0
        blur = img.get("blur", -1)
        # PPTX widths in EMU when from python-docx; for parse_pptx we convert to pixels
        if w and w > 100000:  # likely EMU (914400 EMU per inch)
            w_px = int(w / 9525)
            h_px = int(h / 9525)
        else:
            w_px, h_px = w, h
        too_small = (
            w_px and h_px and (w_px < settings["min_image_width"] or h_px < settings["min_image_height"])
        )
        too_blurry = 0 < blur < settings["blur_variance_threshold"]
        if too_small or too_blurry:
            bad.append(f"{w_px}x{h_px}px blur={blur:.1f}")
    if not bad:
        return RuleResult("C11", "C", "Qualité des images (résolution, netteté)", PASS, MAJOR,
                          evidence=f"{len(p.images)} images OK")
    return RuleResult(
        "C11", "C", "Qualité des images (résolution, netteté)", WARN, MAJOR,
        evidence=f"{len(bad)} image(s) sous seuil: " + "; ".join(bad[:5]),
        recommendation="Remplacer par des images haute résolution / non floues.",
    )


def rule_table_no_merge(p: ParsedDoc) -> RuleResult:
    if not p.tables:
        return RuleResult("D12", "D", "Pas de cellules fusionnées", PASS, BLOCKER, evidence="Aucun tableau")
    merged = [t for t in p.tables if t.get("merged")]
    if not merged:
        return RuleResult("D12", "D", "Pas de cellules fusionnées", PASS, BLOCKER,
                          evidence=f"{len(p.tables)} tableau(x) sans fusion")
    return RuleResult(
        "D12", "D", "Pas de cellules fusionnées", FAIL, BLOCKER,
        evidence=f"{len(merged)} tableau(x) avec cellules fusionnées",
        recommendation="Dé-fusionner les cellules pour permettre une lecture machine.",
    )


def rule_table_borders(p: ParsedDoc) -> RuleResult:
    if not p.tables:
        return RuleResult("D13", "D", "Bordures de tableaux visibles", PASS, MINOR, evidence="Aucun tableau")
    if p.file_type != "xlsx":
        return RuleResult("D13", "D", "Bordures de tableaux visibles", NV, MINOR,
                          evidence="Vérification automatique limitée hors XLSX")
    no_border = [t for t in p.tables if not t.get("borders")]
    if not no_border:
        return RuleResult("D13", "D", "Bordures de tableaux visibles", PASS, MAJOR,
                          evidence="Bordures détectées sur toutes les feuilles")
    return RuleResult(
        "D13", "D", "Bordures de tableaux visibles", WARN, MAJOR,
        evidence=f"{len(no_border)} feuille(s) sans bordure détectée",
        recommendation="Appliquer des bordures noires fines sur les tableaux.",
    )


def rule_table_headers(p: ParsedDoc) -> RuleResult:
    if not p.tables:
        return RuleResult("D14", "D", "En-têtes de tableau mis en valeur", PASS, MAJOR, evidence="Aucun tableau")
    weak = [t for t in p.tables if not t.get("header_bold")]
    if not weak:
        return RuleResult("D14", "D", "En-têtes de tableau mis en valeur", PASS, MAJOR,
                          evidence="Première ligne en gras pour tous les tableaux")
    return RuleResult(
        "D14", "D", "En-têtes de tableau mis en valeur", WARN, MAJOR,
        evidence=f"{len(weak)} tableau(x) sans en-tête en gras",
        recommendation="Mettre la première ligne en gras et/ou utiliser un fond distinct.",
    )


def rule_table_titles(p: ParsedDoc) -> RuleResult:
    if not p.tables:
        return RuleResult("D15", "D", "Titre + légende au-dessus des tableaux", PASS, MAJOR, evidence="Aucun tableau")
    text = _full_text(p).lower()
    mentions = text.count("tableau")
    if mentions >= len(p.tables):
        return RuleResult(
            "D15", "D", "Titre + légende au-dessus des tableaux", PASS, MAJOR,
            evidence=f"{mentions} mentions 'Tableau' / {len(p.tables)} tableaux",
        )
    return RuleResult(
        "D15", "D", "Titre + légende au-dessus des tableaux", WARN, MAJOR,
        evidence=f"{mentions} mentions 'Tableau' / {len(p.tables)} tableaux",
        recommendation="Ajouter un titre 'Tableau X – ...' et une légende explicite.",
    )


def rule_table_symbols(p: ParsedDoc) -> RuleResult:
    if not p.tables:
        return RuleResult("D16", "D", "Pas de symboles dans les cellules", PASS, MAJOR, evidence="Aucun tableau")
    bad = 0
    samples = []
    for t in p.tables:
        for row in t.get("rows", []):
            for cell in row:
                if EMOJI_OR_SYMBOL_RE.search(cell or ""):
                    bad += 1
                    if len(samples) < 5:
                        samples.append(_truncate(cell, 40))
    if bad == 0:
        return RuleResult("D16", "D", "Pas de symboles dans les cellules", PASS, MAJOR,
                          evidence="Aucun symbole détecté")
    return RuleResult(
        "D16", "D", "Pas de symboles dans les cellules", FAIL, MAJOR,
        evidence=f"{bad} cellules contiennent des symboles: {', '.join(samples)}",
        recommendation="Remplacer ✓/✗ par 'oui'/'non' (texte explicite).",
    )


def rule_table_pagination(p: ParsedDoc) -> RuleResult:
    if not p.tables:
        return RuleResult("D17", "D", "Pagination/en-têtes répétés sur tableaux longs", PASS, MINOR,
                          evidence="Aucun tableau")
    return RuleResult(
        "D17", "D", "Pagination/en-têtes répétés sur tableaux longs", NV, MINOR,
        evidence="Non vérifiable automatiquement",
        recommendation="Vérifier manuellement la répétition des en-têtes pour les tableaux multi-pages.",
    )


def rule_table_native(p: ParsedDoc) -> RuleResult:
    text_lower = _full_text(p).lower()
    images_with_table_caption = sum(1 for img in p.images) if "tableau" in text_lower and not p.tables else 0
    if not p.tables and p.images and "tableau" in text_lower:
        return RuleResult(
            "D18", "D", "Tableau natif (pas une image)", FAIL, BLOCKER,
            evidence=f"{len(p.images)} image(s) + mentions 'tableau' mais aucun tableau natif détecté",
            recommendation="Recréer le tableau au format natif (DOCX/PPTX/XLSX).",
        )
    return RuleResult(
        "D18", "D", "Tableau natif (pas une image)", PASS, BLOCKER,
        evidence=f"{len(p.tables)} tableau(x) natif(s)",
    )


def rule_diagrams(p: ParsedDoc) -> RuleResult:
    if p.file_type != "pptx":
        return RuleResult("E19", "E", "Diagrammes lisibles et structurés", NV, MINOR,
                          evidence="Heuristique réservée aux PPTX")
    counts = p.extra.get("diagram_shape_counts", [])
    overloaded = [c for c in counts if c >= 15]
    text = _full_text(p).lower()
    generic = bool(re.search(r"\bétape\s*\d|\bstep\s*\d", text))
    if not overloaded and not generic:
        return RuleResult("E19", "E", "Diagrammes lisibles et structurés", PASS, MINOR,
                          evidence=f"Slides surchargés: 0; libellés génériques: non")
    return RuleResult(
        "E19", "E", "Diagrammes lisibles et structurés", WARN, MINOR,
        evidence=f"{len(overloaded)} slide(s) surchargé(s); libellés génériques={generic}",
        recommendation="Limiter les boîtes/flèches; nommer précisément les éléments (éviter 'Étape 1').",
    )


def rule_url_context(p: ParsedDoc) -> RuleResult:
    if not p.urls:
        return RuleResult("F25", "F", "URLs introduites par un texte de contexte", PASS, MAJOR, evidence="Aucune URL")
    bad = []
    for block in p.text_blocks:
        for line in block.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            m = URL_RE.match(stripped)
            if m and (m.end() - m.start()) >= len(stripped) - 5:
                bad.append(_truncate(stripped, 80))
    if not bad:
        return RuleResult("F25", "F", "URLs introduites par un texte de contexte", PASS, MAJOR,
                          evidence=f"{len(p.urls)} URL(s) avec contexte")
    return RuleResult(
        "F25", "F", "URLs introduites par un texte de contexte", FAIL, MAJOR,
        evidence=f"URL(s) seule(s) sur ligne: {', '.join(bad[:3])}",
        recommendation="Précéder chaque URL d'un texte d'introduction explicite.",
    )


def _clean_url(url: str) -> Tuple[str, List[str]]:
    if "?" not in url:
        return url, []
    base, qs = url.split("?", 1)
    keep, drop = [], []
    for part in qs.split("&"):
        if any(part.lower().startswith(t) for t in TRACKING_PARAMS):
            drop.append(part)
        else:
            keep.append(part)
    cleaned = base + ("?" + "&".join(keep) if keep else "")
    return cleaned, drop


def rule_url_clean(p: ParsedDoc) -> RuleResult:
    if not p.urls:
        return RuleResult("F26", "F", "URLs nettoyées (pas de tracking)", PASS, MAJOR, evidence="Aucune URL")
    dirty = []
    for u in p.urls:
        cleaned, drop = _clean_url(u)
        if drop:
            dirty.append((u, cleaned, drop))
    if not dirty:
        return RuleResult("F26", "F", "URLs nettoyées (pas de tracking)", PASS, MAJOR,
                          evidence=f"{len(p.urls)} URL(s) sans tracking")
    samples = "; ".join(f"{_truncate(u, 60)} → {_truncate(c, 60)}" for u, c, _ in dirty[:3])
    return RuleResult(
        "F26", "F", "URLs nettoyées (pas de tracking)", FAIL, MAJOR,
        evidence=f"{len(dirty)} URL(s) avec params (utm_/token/session): {samples}",
        recommendation="Supprimer les paramètres de tracking avant intégration.",
    )


def rule_url_visible(p: ParsedDoc) -> RuleResult:
    if not p.hyperlinks:
        if p.file_type == "pdf":
            return RuleResult("F27", "F", "URL affichée en clair (pas masquée)", NV, MAJOR,
                              evidence="Hyperliens PDF non analysés")
        return RuleResult("F27", "F", "URL affichée en clair (pas masquée)", PASS, MAJOR, evidence="Aucun hyperlien")
    masked = [(d, t) for d, t in p.hyperlinks if d and t and d.strip() != t.strip() and not d.startswith("http")]
    if not masked:
        return RuleResult("F27", "F", "URL affichée en clair (pas masquée)", PASS, MAJOR,
                          evidence=f"{len(p.hyperlinks)} hyperliens, URL visible")
    samples = "; ".join(f"'{_truncate(d, 30)}' → {_truncate(t, 60)}" for d, t in masked[:3])
    return RuleResult(
        "F27", "F", "URL affichée en clair (pas masquée)", FAIL, MAJOR,
        evidence=f"{len(masked)} lien(s) masqué(s): {samples}",
        recommendation="Afficher l'URL complète plutôt qu'un texte d'ancre.",
    )


def rule_word_breaks(p: ParsedDoc) -> RuleResult:
    text = _full_text(p)
    breaks = len(re.findall(r"-\s*\n", text))
    if breaks <= 2:
        return RuleResult("G28", "G", "Pas de coupures de mots/paragraphes", PASS, MINOR, evidence=f"{breaks} coupures")
    return RuleResult(
        "G28", "G", "Pas de coupures de mots/paragraphes", WARN, MINOR,
        evidence=f"{breaks} coupures détectées",
        recommendation="Désactiver la césure automatique; reflow le texte.",
    )


def rule_format_preference(p: ParsedDoc) -> RuleResult:
    if p.file_type == "docx":
        return RuleResult("G29", "G", "Format DOCX privilégié", PASS, MINOR, evidence="DOCX")
    return RuleResult(
        "G29", "G", "Format DOCX privilégié", WARN, MINOR,
        evidence=f"Format actuel: {p.file_type.upper()}",
        recommendation="Privilégier DOCX pour la maintenabilité du contenu KM.",
    )


def rule_doc_length(p: ParsedDoc, settings: Dict[str, Any]) -> RuleResult:
    if p.pages <= settings["long_doc_pages"]:
        return RuleResult("G30", "G", "Document de longueur raisonnable", PASS, MINOR, evidence=f"{p.pages} pages")
    return RuleResult(
        "G30", "G", "Document de longueur raisonnable", WARN, MINOR,
        evidence=f"{p.pages} pages (> {settings['long_doc_pages']})",
        recommendation="Découper le document en plusieurs livrables thématiques.",
    )


def rule_headers_footers(p: ParsedDoc) -> RuleResult:
    if p.file_type != "docx":
        return RuleResult("G31", "G", "Pas d'en-têtes/pieds de page superflus", NV, MINOR)
    if p.extra.get("has_headers_footers"):
        return RuleResult(
            "G31", "G", "Pas d'en-têtes/pieds de page superflus", WARN, MINOR,
            evidence="En-tête/pied détecté",
            recommendation="Limiter les en-têtes/pieds de page (réduisent la lisibilité IA).",
        )
    return RuleResult("G31", "G", "Pas d'en-têtes/pieds de page superflus", PASS, MINOR)


def rule_short_sentences(p: ParsedDoc, settings: Dict[str, Any]) -> RuleResult:
    text = _full_text(p)
    sentences = re.split(r"[\.\!\?]\s+", text)
    word_counts = [len(s.split()) for s in sentences if s.strip()]
    if not word_counts:
        return RuleResult("G32", "G", "Phrases courtes et simples", NV, MINOR, evidence="Pas de texte")
    avg = sum(word_counts) / len(word_counts)
    if avg <= settings["max_avg_sentence_words"]:
        return RuleResult("G32", "G", "Phrases courtes et simples", PASS, MINOR,
                          evidence=f"Moyenne {avg:.1f} mots/phrase")
    return RuleResult(
        "G32", "G", "Phrases courtes et simples", WARN, MINOR,
        evidence=f"Moyenne {avg:.1f} mots/phrase (> {settings['max_avg_sentence_words']})",
        recommendation="Raccourcir les phrases (cible: 15-20 mots).",
    )


def rule_left_alignment(p: ParsedDoc) -> RuleResult:
    if p.file_type not in {"pptx", "pdf"}:
        return RuleResult("G33", "G", "Alignement à gauche (PPT/PDF)", NV, MINOR)
    text = _full_text(p)
    multiple_spaces = len(re.findall(r"  {2,}", text))
    if multiple_spaces > 20:
        return RuleResult(
            "G33", "G", "Alignement à gauche (PPT/PDF)", WARN, MINOR,
            evidence=f"{multiple_spaces} séquences d'espaces multiples (potentiellement justifié/centré)",
            recommendation="Privilégier un alignement à gauche pour une meilleure lisibilité.",
        )
    return RuleResult("G33", "G", "Alignement à gauche (PPT/PDF)", PASS, MINOR)


# ----- Sensitive data ------

def _mask_email(e: str) -> str:
    try:
        local, domain = e.split("@", 1)
        return (local[0] + "***" if local else "***") + "@" + domain
    except Exception:
        return "***@***"


def _mask_phone(p: str) -> str:
    digits = re.sub(r"\D", "", p)
    if len(digits) < 4:
        return "***"
    return "***" + digits[-2:]


def _mask_iban(s: str) -> str:
    s = s.replace(" ", "")
    if len(s) < 6:
        return "***"
    return s[:2] + "***" + s[-4:]


def rule_sensitive_data(p: ParsedDoc) -> RuleResult:
    text = _full_text(p)
    emails = EMAIL_RE.findall(text)
    phones = PHONE_RE.findall(text)
    ibans = IBAN_RE.findall(text)
    addresses = POSTAL_ADDR_RE.findall(text)
    client_ids = CLIENT_ID_RE.findall(text)

    # Filter author email if cartouche-detected
    author_emails = set()
    head = text[:3000]
    for em in EMAIL_RE.findall(head):
        # If it's near "Auteur" or "Email", consider it author's
        if re.search(r"(auteur|email|contact)", head[: head.find(em) + 1], re.IGNORECASE):
            author_emails.add(em)
    suspicious_emails = [e for e in emails if e not in author_emails]

    findings = []
    if suspicious_emails:
        findings.append(f"emails: {', '.join(_mask_email(e) for e in suspicious_emails[:5])}")
    # phones may overmatch; require non-trivial digit count
    real_phones = [ph for ph in phones if len(re.sub(r"\D", "", ph)) >= 8]
    if real_phones:
        findings.append(f"téléphones: {', '.join(_mask_phone(ph) for ph in real_phones[:5])}")
    if ibans:
        findings.append(f"IBAN: {', '.join(_mask_iban(i) for i in ibans[:3])}")
    if addresses:
        findings.append(f"adresses: {len(addresses)} occurrence(s)")
    if client_ids:
        findings.append(f"identifiants client: {len(client_ids)} occurrence(s)")

    if not findings:
        return RuleResult(
            "H34", "H", "Aucune donnée client / personnelle détectée", PASS, BLOCKER,
            evidence="Aucun pattern sensible détecté",
        )
    return RuleResult(
        "H34", "H", "Aucune donnée client / personnelle détectée", FAIL, BLOCKER,
        evidence=" | ".join(findings),
        recommendation="Anonymiser/retirer toute donnée client/personnelle avant publication KM.",
    )


# ---------------------------------------------------------------------------
# Orchestration & scoring
# ---------------------------------------------------------------------------

ALL_RULES = [
    rule_naming,
    rule_cartouche,
    rule_objective,
    rule_acronyms,
    rule_glossary,
    rule_headings_hierarchy,
    lambda p, s=None: rule_headings_density(p, s),
    rule_textboxes,
    rule_no_symbols_in_sentences,
    rule_image_legends,
    lambda p, s=None: rule_image_quality(p, s),
    rule_table_no_merge,
    rule_table_borders,
    rule_table_headers,
    rule_table_titles,
    rule_table_symbols,
    rule_table_pagination,
    rule_table_native,
    rule_diagrams,
    rule_url_context,
    rule_url_clean,
    rule_url_visible,
    rule_word_breaks,
    rule_format_preference,
    lambda p, s=None: rule_doc_length(p, s),
    rule_headers_footers,
    lambda p, s=None: rule_short_sentences(p, s),
    rule_left_alignment,
    rule_sensitive_data,
]


def run_all_rules(parsed: ParsedDoc, settings: Dict[str, Any]) -> List[RuleResult]:
    results: List[RuleResult] = []
    for fn in ALL_RULES:
        try:
            if fn.__code__.co_argcount == 2:
                results.append(fn(parsed, settings))
            else:
                results.append(fn(parsed))
        except Exception as exc:  # pragma: no cover - defensive
            results.append(
                RuleResult(
                    "ERR",
                    "?",
                    f"Erreur d'évaluation ({getattr(fn, '__name__', 'rule')})",
                    NV,
                    MINOR,
                    evidence=str(exc),
                )
            )
    return results


def compute_score_and_verdict(rules: List[RuleResult], settings: Dict[str, Any]) -> Tuple[float, str]:
    blocking = [r for r in rules if r.severity == BLOCKER]
    practices = [r for r in rules if r.severity != BLOCKER]

    def _ratio(items: List[RuleResult]) -> float:
        if not items:
            return 1.0
        weights = {PASS: 1.0, WARN: 0.5, NV: 0.7, FAIL: 0.0}
        return sum(weights.get(r.status, 0.0) for r in items) / len(items)

    score = (
        _ratio(blocking) * settings["weight_blocking"]
        + _ratio(practices) * settings["weight_practices"]
    )
    has_blocker_fail = any(r.is_blocker_fail() for r in rules)
    verdict = "Feu Rouge" if has_blocker_fail else (
        "Feu Vert" if score >= settings["score_pass_threshold"] else "Feu Orange"
    )
    return round(score, 1), verdict


def audit_document(file_name: str, raw: bytes, settings: Dict[str, Any]) -> DocumentAuditResult:
    parsed = parse_document(file_name, raw)
    res = DocumentAuditResult(
        file_name=file_name,
        file_type=parsed.file_type,
        file_size=len(raw),
        audit_date=_dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        parse_error=parsed.parse_warning,
    )
    res.rules = run_all_rules(parsed, settings)
    res.metrics = {
        "pages": parsed.pages,
        "headings": len(parsed.headings),
        "tables": len(parsed.tables),
        "images": len(parsed.images),
        "urls": len(parsed.urls),
        "hyperlinks": len(parsed.hyperlinks),
        "text_blocks": len(parsed.text_blocks),
    }
    res.score, res.verdict = compute_score_and_verdict(res.rules, settings)
    return res


# ---------------------------------------------------------------------------
# PDF report (ReportLab)
# ---------------------------------------------------------------------------


def _verdict_color(verdict: str):
    return {
        "Feu Vert": colors.HexColor("#2e7d32"),
        "Feu Orange": colors.HexColor("#ef6c00"),
        "Feu Rouge": colors.HexColor("#c62828"),
    }.get(verdict, colors.grey)


def _status_color(status: str):
    return {
        PASS: colors.HexColor("#2e7d32"),
        FAIL: colors.HexColor("#c62828"),
        WARN: colors.HexColor("#ef6c00"),
        NV: colors.HexColor("#616161"),
    }.get(status, colors.black)


def generate_pdf_report(result: DocumentAuditResult) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=1.5 * cm, rightMargin=1.5 * cm,
        topMargin=1.5 * cm, bottomMargin=1.5 * cm,
        title=f"KM Audit - {result.file_name}",
    )
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], textColor=colors.HexColor("#0d3b66"))
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], textColor=colors.HexColor("#0d3b66"))
    body = styles["BodyText"]
    flow: List[Any] = []

    flow.append(Paragraph("Rapport d'audit KM / IA-readiness", h1))
    flow.append(Spacer(1, 0.3 * cm))

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
    flow.append(cart_table)
    flow.append(Spacer(1, 0.5 * cm))

    if result.parse_error:
        flow.append(Paragraph(f"<b>Avertissement parsing:</b> {result.parse_error}", body))
        flow.append(Spacer(1, 0.3 * cm))

    blockers = result.blocking_failures
    flow.append(Paragraph("Synthèse des non-conformités", h2))
    if blockers:
        rows = [["Règle", "Catégorie", "Sévérité", "Preuve / Recommandation"]]
        for r in blockers:
            rows.append(
                [
                    f"{r.rule_id} – {r.title}",
                    CATEGORIES.get(r.category, r.category),
                    r.severity,
                    Paragraph(
                        f"<b>{_truncate(r.evidence, 220)}</b><br/>{_truncate(r.recommendation, 220)}",
                        body,
                    ),
                ]
            )
        t = Table(rows, colWidths=[5 * cm, 3 * cm, 2 * cm, 7 * cm], repeatRows=1)
        t.setStyle(_default_table_style(header_color="#c62828"))
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
                    r.status,
                    r.severity,
                    Paragraph(_truncate(r.evidence, 240), body),
                    Paragraph(_truncate(r.recommendation, 240), body),
                ]
            )
        t = Table(rows, colWidths=[4.5 * cm, 1.8 * cm, 1.6 * cm, 4.6 * cm, 4.5 * cm], repeatRows=1)
        t.setStyle(_default_table_style())
        for i, r in enumerate(cat_rules, start=1):
            t.setStyle(
                TableStyle(
                    [("TEXTCOLOR", (1, i), (1, i), _status_color(r.status))]
                )
            )
        flow.append(KeepTogether(t))
        flow.append(Spacer(1, 0.3 * cm))

    flow.append(PageBreak())
    flow.append(Paragraph("Annexe – Métriques détectées", h2))
    metric_rows = [["Métrique", "Valeur"]] + [[k, str(v)] for k, v in result.metrics.items()]
    mt = Table(metric_rows, colWidths=[6 * cm, 6 * cm])
    mt.setStyle(_default_table_style())
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


def _default_table_style(header_color: str = "#0d3b66") -> TableStyle:
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


# ---------------------------------------------------------------------------
# Streamlit UI
# ---------------------------------------------------------------------------


@st.cache_data(show_spinner=False)
def _cached_audit(file_name: str, raw: bytes, settings_key: Tuple) -> DocumentAuditResult:
    settings = dict(settings_key)
    return audit_document(file_name, raw, settings)


def _settings_panel() -> Dict[str, Any]:
    s = dict(DEFAULT_SETTINGS)
    st.sidebar.header("Paramètres")
    s["max_paragraph_chars"] = st.sidebar.number_input(
        "Longueur max paragraphe (chars)", 100, 5000, s["max_paragraph_chars"], 50
    )
    s["max_avg_sentence_words"] = st.sidebar.number_input(
        "Longueur moyenne max phrase (mots)", 5, 60, s["max_avg_sentence_words"], 1
    )
    s["min_image_width"] = st.sidebar.number_input("Largeur min image (px)", 100, 5000, s["min_image_width"], 50)
    s["min_image_height"] = st.sidebar.number_input("Hauteur min image (px)", 100, 5000, s["min_image_height"], 50)
    s["blur_variance_threshold"] = st.sidebar.number_input(
        "Seuil flou (variance Laplacien)", 0.0, 5000.0, float(s["blur_variance_threshold"]), 5.0
    )
    s["long_doc_pages"] = st.sidebar.number_input("Document long si > N pages", 1, 200, s["long_doc_pages"], 1)
    s["min_headings_per_pages"] = st.sidebar.slider(
        "Densité min titres / page", 0.0, 5.0, float(s["min_headings_per_pages"]), 0.1
    )
    s["score_pass_threshold"] = st.sidebar.slider("Seuil de conformité (Feu Vert)", 0, 100, s["score_pass_threshold"])
    s["weight_blocking"] = st.sidebar.slider("Poids des règles bloquantes", 0, 100, s["weight_blocking"])
    s["weight_practices"] = 100 - s["weight_blocking"]
    st.sidebar.caption(f"Poids bonnes pratiques: {s['weight_practices']}")
    return s


def _render_rules_doc():
    st.subheader("Checklist appliquée")
    for cat_code, cat_label in CATEGORIES.items():
        st.markdown(f"### {cat_code} – {cat_label}")
        st.write(_RULES_DOC.get(cat_code, "—"))


_RULES_DOC = {
    "A": "A1 nommage, A2 cartouche, A3 objectif, A4 acronymes 1re occurrence, A5 glossaire (BLOQUANT).",
    "B": "B6 hiérarchie de titres, B7 densité de titres, B8 textboxes inutiles (PPTX), B9 symboles dans phrases.",
    "C": "C10 légendes d'images, C11 résolution + variance Laplacien (flou).",
    "D": "D12 fusions, D13 bordures (XLSX), D14 en-têtes en gras, D15 titres/légendes, D16 symboles, "
         "D17 pagination (NV), D18 tableau natif vs image.",
    "E": "E19 lisibilité diagrammes (heuristique PPTX: nb shapes, libellés génériques).",
    "F": "F25 contexte autour des URLs, F26 nettoyage (utm/token/session), F27 URL en clair.",
    "G": "G28 coupures, G29 DOCX préféré, G30 longueur, G31 en-têtes/pieds, G32 phrases courtes, G33 alignement.",
    "H": "H34 détection emails / téléphones / IBAN / adresses / identifiants client (masqués dans le rapport).",
}


def _render_audit_summary(res: DocumentAuditResult):
    badge_color = {"Feu Vert": "🟢", "Feu Orange": "🟠", "Feu Rouge": "🔴"}.get(res.verdict, "⚪")
    cols = st.columns([2, 1, 1])
    cols[0].markdown(f"### {badge_color} **{res.file_name}** — {res.verdict}")
    cols[1].metric("Score", f"{res.score}/100")
    cols[2].metric("Bloquants KO", len(res.blocking_failures))
    if res.parse_error:
        st.warning(res.parse_error)
    if res.blocking_failures:
        st.error("Points bloquants:")
        for r in res.blocking_failures:
            st.markdown(f"- **{r.rule_id} {r.title}** — {_truncate(r.evidence, 200)}")


def _render_rules_table(res: DocumentAuditResult):
    with st.expander("Détail des règles", expanded=False):
        for cat_code, cat_label in CATEGORIES.items():
            cat_rules = [r for r in res.rules if r.category == cat_code]
            if not cat_rules:
                continue
            st.markdown(f"**{cat_code} – {cat_label}**")
            for r in cat_rules:
                icon = {"PASS": "✅", "FAIL": "❌", "WARN": "⚠️", "NOT_VERIFIABLE": "❔"}.get(r.status, "•")
                st.markdown(
                    f"{icon} `{r.rule_id}` **{r.title}** "
                    f"_(sévérité: {r.severity})_  \n"
                    f"&nbsp;&nbsp;Preuve: {_truncate(r.evidence, 240) or '—'}  \n"
                    f"&nbsp;&nbsp;Reco: {_truncate(r.recommendation, 240) or '—'}"
                )


def main_streamlit():
    st.set_page_config(page_title="KM Document Audit", page_icon="📋", layout="wide")
    st.title("📋 KM Document Audit – Quality Gate IA-readiness")
    st.caption("Audit local et offline – aucun appel réseau.")

    settings = _settings_panel()
    settings_key = tuple(sorted(settings.items()))

    tab_audit, tab_rules = st.tabs(["Audit", "Règles / Checklist"])

    with tab_rules:
        _render_rules_doc()

    with tab_audit:
        files = st.file_uploader(
            "Glisser-déposer un ou plusieurs documents (DOCX, PPTX, PDF, XLSX)",
            type=["docx", "pptx", "pdf", "xlsx"],
            accept_multiple_files=True,
        )
        if not files:
            st.info("Aucun fichier chargé pour l'instant.")
            return

        results: List[DocumentAuditResult] = []
        reports: List[Tuple[str, bytes]] = []
        for f in files:
            raw = f.getvalue()
            try:
                res = _cached_audit(f.name, raw, settings_key)
            except Exception as exc:  # pragma: no cover
                st.error(f"Erreur d'audit ({f.name}): {exc}")
                continue
            results.append(res)

            with st.container(border=True):
                _render_audit_summary(res)
                _render_rules_table(res)
                pdf_bytes = generate_pdf_report(res)
                reports.append((pdf_filename(res.file_name), pdf_bytes))
                st.download_button(
                    label=f"📄 Générer PDF – {res.file_name}",
                    data=pdf_bytes,
                    file_name=pdf_filename(res.file_name),
                    mime="application/pdf",
                    key=f"pdf_{res.file_name}",
                )

        if len(reports) > 1:
            st.markdown("---")
            zip_bytes = generate_zip(reports)
            st.download_button(
                "🗂 Tout télécharger (ZIP)",
                data=zip_bytes,
                file_name=f"KM_AUDIT_{_dt.date.today().strftime('%Y%m%d')}.zip",
                mime="application/zip",
            )


# ---------------------------------------------------------------------------
# Self-check
# ---------------------------------------------------------------------------


def self_check() -> int:
    """Light, dependency-free sanity tests for regex/heuristics."""
    failures = 0

    def check(label: str, cond: bool):
        nonlocal failures
        print(("OK  " if cond else "FAIL") + " " + label)
        if not cond:
            failures += 1

    check(
        "naming valid",
        bool(NAMING_REGEX.match("20260121_Guidelines_KM_Cash.pptx")),
    )
    check(
        "naming invalid",
        not NAMING_REGEX.match("guidelines.pptx"),
    )

    cleaned, drop = _clean_url("https://x.com/a?utm_source=foo&id=42&token=abc")
    check("url cleaning drops tracking", "utm_source=foo" in drop and "token=abc" in drop)
    check("url cleaning keeps id", "id=42" in cleaned)

    text = "We use API to call the API. The API (Application Programming Interface) is..."
    check("acronym pattern", bool(ACRONYM_RE.search(text)))

    check("email mask", _mask_email("john.doe@example.com").endswith("@example.com"))
    check("iban mask shorter", len(_mask_iban("FR7612345678901234567890123")) < 27)

    print(f"\n{failures} failure(s)")
    return failures


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if "--self-check" in sys.argv[1:]:
        sys.exit(self_check())
    # Streamlit sets __name__ to "__main__" when running `streamlit run app.py`
    main_streamlit()
