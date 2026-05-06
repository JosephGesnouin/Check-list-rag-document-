"""Category B – Structure (titles, hierarchy, textboxes, symbols)."""
from __future__ import annotations

from ..config import EMOJI_OR_SYMBOL_RE, Settings
from ..models import ParsedDoc, RuleResult, Severity, Status
from . import register
from ._helpers import truncate


@register
def rule_headings_hierarchy(p: ParsedDoc, _: Settings) -> RuleResult:
    if not p.headings:
        return RuleResult(
            "B6", "B", "Titres descriptifs et hiérarchisés",
            Status.FAIL, Severity.BLOCKER,
            recommendation="Utiliser les styles Heading/Titre de slide pour structurer le contenu.",
        )
    levels = sorted({lvl for lvl, _t in p.headings})
    multi_level = len(levels) >= 2 or p.file_type == "pptx"
    descriptive = all(2 <= len(t.split()) <= 18 for _l, t in p.headings)
    if multi_level and descriptive:
        return RuleResult(
            "B6", "B", "Titres descriptifs et hiérarchisés",
            Status.PASS, Severity.BLOCKER,
            evidence=f"{len(p.headings)} titres, niveaux={levels}",
        )
    return RuleResult(
        "B6", "B", "Titres descriptifs et hiérarchisés",
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
            "B7", "B", "Densité de titres suffisante",
            Status.PASS, Severity.BLOCKER,
            evidence=f"{len(p.headings)} titres / {pages} pages (ratio={ratio:.2f})",
        )
    return RuleResult(
        "B7", "B", "Densité de titres suffisante",
        Status.FAIL, Severity.BLOCKER,
        evidence=f"{len(p.headings)} titres / {pages} pages (ratio={ratio:.2f})",
        recommendation="Ajouter des titres/sous-titres (au moins 1 toutes les 1-2 pages).",
    )


@register
def rule_textboxes(p: ParsedDoc, _: Settings) -> RuleResult:
    if p.file_type == "pptx":
        n = p.extra.get("standalone_textboxes", 0)
        if n <= 2:
            return RuleResult(
                "B8", "B", "Pas de boîtes/cadres inutiles",
                Status.PASS, Severity.BLOCKER, evidence=f"{n} textbox(es) hors titre",
            )
        return RuleResult(
            "B8", "B", "Pas de boîtes/cadres inutiles",
            Status.FAIL, Severity.BLOCKER,
            evidence=f"{n} textbox(es) hors titre détectés",
            recommendation="Limiter les zones de texte flottantes; privilégier les placeholders.",
        )
    return RuleResult(
        "B8", "B", "Pas de boîtes/cadres inutiles",
        Status.NOT_VERIFIABLE, Severity.MAJOR,
        evidence="Détection automatique limitée hors PPTX",
    )


@register
def rule_no_symbols_in_sentences(p: ParsedDoc, _: Settings) -> RuleResult:
    offenders = []
    for block in p.text_blocks:
        for line in block.splitlines():
            if EMOJI_OR_SYMBOL_RE.search(line) and len(line.split()) >= 4:
                offenders.append(truncate(line, 120))
                if len(offenders) >= 5:
                    break
        if len(offenders) >= 5:
            break
    if not offenders:
        return RuleResult(
            "B9", "B", "Pas de symboles/icônes dans les phrases",
            Status.PASS, Severity.BLOCKER,
        )
    return RuleResult(
        "B9", "B", "Pas de symboles/icônes dans les phrases",
        Status.FAIL, Severity.BLOCKER,
        evidence=" | ".join(offenders),
        recommendation="Remplacer les symboles (✓, ➜, etc.) par des mots équivalents.",
        remediable=True,
    )
