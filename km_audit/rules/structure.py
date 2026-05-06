"""Catégorie B — Mise en forme du document et sa structure (BLOQUANT).

Items officiels :
  B5  Les titres sont-ils descriptifs, hiérarchisés et correctement formatés ?
  B6  Les titres et sous-titres sont-ils suffisants ?
"""
from __future__ import annotations

from ..config import Settings
from ..models import ParsedDoc, RuleResult, Severity, Status
from . import register


@register
def rule_headings_hierarchy(p: ParsedDoc, _: Settings) -> RuleResult:
    if not p.headings:
        return RuleResult(
            "B5", "B", "Titres descriptifs, hiérarchisés et correctement formatés",
            Status.FAIL, Severity.BLOCKER,
            recommendation="Utiliser les styles Heading/Titre de slide pour structurer le contenu.",
        )
    levels = sorted({lvl for lvl, _t in p.headings})
    multi_level = len(levels) >= 2 or p.file_type == "pptx"
    descriptive = all(2 <= len(t.split()) <= 18 for _l, t in p.headings)
    if multi_level and descriptive:
        return RuleResult(
            "B5", "B", "Titres descriptifs, hiérarchisés et correctement formatés",
            Status.PASS, Severity.BLOCKER,
            evidence=f"{len(p.headings)} titres, niveaux={levels}",
        )
    return RuleResult(
        "B5", "B", "Titres descriptifs, hiérarchisés et correctement formatés",
        Status.WARN, Severity.BLOCKER,
        evidence=f"{len(p.headings)} titres, niveaux={levels}",
        recommendation="Vérifier la hiérarchie (H1/H2/H3) et le caractère descriptif des titres.",
    )


@register
def rule_headings_density(p: ParsedDoc, settings: Settings) -> RuleResult:
    pages = max(1, p.pages)
    ratio = len(p.headings) / pages
    if ratio >= settings.min_headings_per_pages:
        return RuleResult(
            "B6", "B", "Titres et sous-titres suffisants",
            Status.PASS, Severity.BLOCKER,
            evidence=f"{len(p.headings)} titres / {pages} pages (ratio={ratio:.2f})",
        )
    return RuleResult(
        "B6", "B", "Titres et sous-titres suffisants",
        Status.FAIL, Severity.BLOCKER,
        evidence=f"{len(p.headings)} titres / {pages} pages (ratio={ratio:.2f})",
        recommendation="Ajouter des titres/sous-titres (au moins 1 toutes les 1-2 pages).",
    )
