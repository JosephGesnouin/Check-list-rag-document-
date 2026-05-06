"""KM Document Audit – offline quality gates for KM/AI-ready documents."""
from .audit import audit_document
from .config import Settings, DEFAULT_SETTINGS, CATEGORIES
from .models import (
    DocumentAuditResult,
    ParsedDoc,
    RuleResult,
    Severity,
    Status,
)
from .remediation import (
    RemediationAction,
    RemediationPlan,
    build_plan,
    patch_document,
    render_markdown_guide,
)
from .reporting import generate_pdf_report, generate_zip, pdf_filename

__all__ = [
    "audit_document",
    "Settings",
    "DEFAULT_SETTINGS",
    "CATEGORIES",
    "DocumentAuditResult",
    "ParsedDoc",
    "RuleResult",
    "Severity",
    "Status",
    "RemediationAction",
    "RemediationPlan",
    "build_plan",
    "patch_document",
    "render_markdown_guide",
    "generate_pdf_report",
    "generate_zip",
    "pdf_filename",
]
