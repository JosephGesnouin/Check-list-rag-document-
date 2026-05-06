"""Category E – Diagrams (PPTX heuristics)."""
from __future__ import annotations

import re

from ..config import Settings
from ..models import ParsedDoc, RuleResult, Severity, Status
from . import register
from ._helpers import full_text


@register
def rule_diagrams(p: ParsedDoc, _: Settings) -> RuleResult:
    if p.file_type != "pptx":
        return RuleResult(
            "E19", "E", "Diagrammes lisibles et structurés",
            Status.NOT_VERIFIABLE, Severity.MINOR,
            evidence="Heuristique réservée aux PPTX",
        )
    counts = p.extra.get("diagram_shape_counts", [])
    overloaded = [c for c in counts if c >= 15]
    text = full_text(p).lower()
    generic_labels = bool(re.search(r"\bétape\s*\d|\bstep\s*\d", text))
    if not overloaded and not generic_labels:
        return RuleResult(
            "E19", "E", "Diagrammes lisibles et structurés",
            Status.PASS, Severity.MINOR,
            evidence="Aucun slide surchargé / libellé générique détecté",
        )
    return RuleResult(
        "E19", "E", "Diagrammes lisibles et structurés",
        Status.WARN, Severity.MINOR,
        evidence=f"{len(overloaded)} slide(s) surchargé(s); libellés génériques={generic_labels}",
        recommendation="Limiter les boîtes/flèches; nommer précisément les éléments (éviter 'Étape 1').",
    )
