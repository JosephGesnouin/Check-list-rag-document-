"""High-level entry point: parse + run rules + score."""
from __future__ import annotations

import datetime as _dt

from . import loaders, rules, scoring
from .config import Settings
from .models import DocumentAuditResult


def audit_document(file_name: str, raw: bytes, settings: Settings) -> DocumentAuditResult:
    parsed = loaders.load(file_name, raw)
    result = DocumentAuditResult(
        file_name=file_name,
        file_type=parsed.file_type,
        file_size=len(raw),
        audit_date=_dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        parse_error=parsed.parse_warning,
    )
    result.rules = rules.run_all(parsed, settings)
    result.metrics = {
        "pages": parsed.pages,
        "headings": len(parsed.headings),
        "tables": len(parsed.tables),
        "images": len(parsed.images),
        "urls": len(parsed.urls),
        "hyperlinks": len(parsed.hyperlinks),
        "text_blocks": len(parsed.text_blocks),
    }
    result.score, result.verdict = scoring.compute(result.rules, settings)
    return result
