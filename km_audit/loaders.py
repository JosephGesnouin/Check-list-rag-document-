"""Document loaders. Each loader fills a ParsedDoc from raw bytes.

Optional dependencies are imported lazily; missing libraries produce a
parse_warning instead of crashing.
"""
from __future__ import annotations

import io
import os
import re
from typing import Callable, Dict

from .config import URL_RE
from .models import ParsedDoc

try:  # python-docx
    from docx import Document as DocxDocument
    from docx.oxml.ns import qn as _docx_qn
except Exception:  # pragma: no cover
    DocxDocument = None
    _docx_qn = None

try:  # python-pptx
    from pptx import Presentation
except Exception:  # pragma: no cover
    Presentation = None

try:  # openpyxl
    import openpyxl
except Exception:  # pragma: no cover
    openpyxl = None

try:  # PyPDF2
    from PyPDF2 import PdfReader
except Exception:  # pragma: no cover
    PdfReader = None

try:  # Pillow / numpy for image quality
    from PIL import Image, ImageFilter
    import numpy as np
except Exception:  # pragma: no cover
    Image = None
    ImageFilter = None
    np = None


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def load(file_name: str, raw: bytes) -> ParsedDoc:
    """Dispatch to the right format loader based on extension."""
    ext = os.path.splitext(file_name)[1].lower().lstrip(".")
    parsed = ParsedDoc(file_name=file_name, file_type=ext, raw_bytes=raw)
    loader = _LOADERS.get(ext)
    if loader is None:
        parsed.parse_warning = f"Format non supporté: .{ext}"
        return parsed
    try:
        loader(parsed)
    except Exception as exc:  # pragma: no cover - defensive
        parsed.parse_warning = f"Erreur de parsing: {exc}"
    return parsed


# ---------------------------------------------------------------------------
# Image quality helper
# ---------------------------------------------------------------------------

def laplacian_variance(img) -> float:
    """Approximate sharpness via variance of a 3x3 Laplacian filter."""
    if Image is None or np is None:
        return -1.0
    try:
        gray = img.convert("L")
        kernel = ImageFilter.Kernel(
            (3, 3), [0, 1, 0, 1, -4, 1, 0, 1, 0], scale=1, offset=0
        )
        filtered = gray.filter(kernel)
        return float(np.asarray(filtered, dtype=np.float32).var())
    except Exception:
        return -1.0


# ---------------------------------------------------------------------------
# DOCX
# ---------------------------------------------------------------------------

def _load_docx(p: ParsedDoc) -> None:
    if DocxDocument is None:
        p.parse_warning = "python-docx non installé"
        return
    doc = DocxDocument(io.BytesIO(p.raw_bytes))

    body_paragraphs = []
    for para in doc.paragraphs:
        text = (para.text or "").strip()
        if not text:
            continue
        body_paragraphs.append(text)
        style_name = (para.style.name or "") if para.style else ""
        m = re.match(r"Heading\s+(\d)", style_name)
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

    for rel in doc.part.rels.values():
        if rel.reltype.endswith("/hyperlink"):
            target = rel.target_ref or ""
            if target.startswith("http"):
                p.urls.append(target)
                p.hyperlinks.append((target, target))

    # URLs présentes en texte brut (sans hyperlien Word).
    p.urls.extend(URL_RE.findall("\n".join(body_paragraphs)))

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


# ---------------------------------------------------------------------------
# PPTX
# ---------------------------------------------------------------------------

def _load_pptx(p: ParsedDoc) -> None:
    if Presentation is None:
        p.parse_warning = "python-pptx non installé"
        return
    prs = Presentation(io.BytesIO(p.raw_bytes))
    standalone_textboxes = 0
    diagram_shape_counts = []

    for idx, slide in enumerate(prs.slides, start=1):
        slide_text = []
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
                        standalone_textboxes += 1
            if getattr(shape, "shape_type", None) == 13 and Image is not None:
                try:
                    img = Image.open(io.BytesIO(shape.image.blob))
                    p.images.append(
                        {
                            "width": img.width,
                            "height": img.height,
                            "blur": laplacian_variance(img),
                            "slide": idx,
                        }
                    )
                except Exception:
                    p.images.append({"width": 0, "height": 0, "slide": idx})
            if shape.has_table:
                tbl = shape.table
                rows = [[c.text.strip() for c in r.cells] for r in tbl.rows]
                merged = any(
                    getattr(c, "is_merge_origin", False) or getattr(c, "is_spanned", False)
                    for r in tbl.rows
                    for c in r.cells
                )
                p.tables.append({"rows": rows, "merged": merged, "source": "native", "slide": idx})

        diagram_shape_counts.append(shape_count)
        p.text_blocks.append("\n".join(slide_text))

    p.urls.extend(URL_RE.findall("\n".join(p.text_blocks)))
    p.pages = len(prs.slides)
    p.extra["standalone_textboxes"] = standalone_textboxes
    p.extra["diagram_shape_counts"] = diagram_shape_counts


# ---------------------------------------------------------------------------
# XLSX
# ---------------------------------------------------------------------------

def _load_xlsx(p: ParsedDoc) -> None:
    if openpyxl is None:
        p.parse_warning = "openpyxl non installé"
        return
    wb = openpyxl.load_workbook(io.BytesIO(p.raw_bytes), data_only=True)
    props = wb.properties
    p.extra["xlsx_props"] = {
        "title": props.title,
        "creator": props.creator,
        "subject": props.subject,
        "description": props.description,
        "keywords": props.keywords,
    }

    for ws in wb.worksheets:
        rows = [
            [str(c).strip() if c is not None else "" for c in row]
            for row in ws.iter_rows(values_only=True)
        ]
        merged = bool(ws.merged_cells.ranges)
        first_row_bold = False
        try:
            first_row_bold = any(
                (cell.font and cell.font.bold)
                for cell in next(ws.iter_rows(min_row=1, max_row=1))
            )
        except StopIteration:
            pass
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


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

def _load_pdf(p: ParsedDoc) -> None:
    if PdfReader is None:
        p.parse_warning = "PyPDF2 non installé"
        return
    reader = PdfReader(io.BytesIO(p.raw_bytes))
    pages_text = []
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
    for line in full.splitlines():
        s = line.strip()
        if 2 < len(s) < 80 and (
            re.match(r"^\d+(\.\d+)*\s+\S", s)
            or (s.upper() == s and len(s.split()) <= 8 and any(c.isalpha() for c in s))
        ):
            p.headings.append((1 if not re.match(r"^\d+\.\d", s) else 2, s))
    p.urls = URL_RE.findall(full)


_LOADERS: Dict[str, Callable[[ParsedDoc], None]] = {
    "docx": _load_docx,
    "pptx": _load_pptx,
    "xlsx": _load_xlsx,
    "pdf": _load_pdf,
}
