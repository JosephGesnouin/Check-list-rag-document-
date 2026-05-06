"""Category D – Tables."""
from __future__ import annotations

from ..config import EMOJI_OR_SYMBOL_RE, Settings
from ..models import ParsedDoc, RuleResult, Severity, Status
from . import register
from ._helpers import full_text, truncate


@register
def rule_table_no_merge(p: ParsedDoc, _: Settings) -> RuleResult:
    if not p.tables:
        return RuleResult(
            "D12", "D", "Pas de cellules fusionnées",
            Status.PASS, Severity.BLOCKER, evidence="Aucun tableau",
        )
    merged = [t for t in p.tables if t.get("merged")]
    if not merged:
        return RuleResult(
            "D12", "D", "Pas de cellules fusionnées",
            Status.PASS, Severity.BLOCKER,
            evidence=f"{len(p.tables)} tableau(x) sans fusion",
        )
    return RuleResult(
        "D12", "D", "Pas de cellules fusionnées",
        Status.FAIL, Severity.BLOCKER,
        evidence=f"{len(merged)} tableau(x) avec cellules fusionnées",
        recommendation="Dé-fusionner les cellules pour permettre une lecture machine.",
    )


@register
def rule_table_borders(p: ParsedDoc, _: Settings) -> RuleResult:
    if not p.tables:
        return RuleResult(
            "D13", "D", "Bordures de tableaux visibles",
            Status.PASS, Severity.MINOR, evidence="Aucun tableau",
        )
    if p.file_type != "xlsx":
        return RuleResult(
            "D13", "D", "Bordures de tableaux visibles",
            Status.NOT_VERIFIABLE, Severity.MINOR,
            evidence="Vérification automatique limitée hors XLSX",
        )
    no_border = [t for t in p.tables if not t.get("borders")]
    if not no_border:
        return RuleResult(
            "D13", "D", "Bordures de tableaux visibles",
            Status.PASS, Severity.MAJOR,
            evidence="Bordures détectées sur toutes les feuilles",
        )
    return RuleResult(
        "D13", "D", "Bordures de tableaux visibles",
        Status.WARN, Severity.MAJOR,
        evidence=f"{len(no_border)} feuille(s) sans bordure détectée",
        recommendation="Appliquer des bordures noires fines sur les tableaux.",
    )


@register
def rule_table_headers(p: ParsedDoc, _: Settings) -> RuleResult:
    if not p.tables:
        return RuleResult(
            "D14", "D", "En-têtes de tableau mis en valeur",
            Status.PASS, Severity.MAJOR, evidence="Aucun tableau",
        )
    weak = [t for t in p.tables if not t.get("header_bold")]
    if not weak:
        return RuleResult(
            "D14", "D", "En-têtes de tableau mis en valeur",
            Status.PASS, Severity.MAJOR,
            evidence="Première ligne en gras pour tous les tableaux",
        )
    return RuleResult(
        "D14", "D", "En-têtes de tableau mis en valeur",
        Status.WARN, Severity.MAJOR,
        evidence=f"{len(weak)} tableau(x) sans en-tête en gras",
        recommendation="Mettre la première ligne en gras et/ou utiliser un fond distinct.",
    )


@register
def rule_table_titles(p: ParsedDoc, _: Settings) -> RuleResult:
    if not p.tables:
        return RuleResult(
            "D15", "D", "Titre + légende au-dessus des tableaux",
            Status.PASS, Severity.MAJOR, evidence="Aucun tableau",
        )
    text = full_text(p).lower()
    mentions = text.count("tableau")
    if mentions >= len(p.tables):
        return RuleResult(
            "D15", "D", "Titre + légende au-dessus des tableaux",
            Status.PASS, Severity.MAJOR,
            evidence=f"{mentions} mentions 'Tableau' / {len(p.tables)} tableaux",
        )
    return RuleResult(
        "D15", "D", "Titre + légende au-dessus des tableaux",
        Status.WARN, Severity.MAJOR,
        evidence=f"{mentions} mentions 'Tableau' / {len(p.tables)} tableaux",
        recommendation="Ajouter un titre 'Tableau X – ...' et une légende explicite.",
    )


@register
def rule_table_symbols(p: ParsedDoc, _: Settings) -> RuleResult:
    if not p.tables:
        return RuleResult(
            "D16", "D", "Pas de symboles dans les cellules",
            Status.PASS, Severity.MAJOR, evidence="Aucun tableau",
        )
    bad = 0
    samples = []
    for t in p.tables:
        for row in t.get("rows", []):
            for cell in row:
                if EMOJI_OR_SYMBOL_RE.search(cell or ""):
                    bad += 1
                    if len(samples) < 5:
                        samples.append(truncate(cell, 40))
    if bad == 0:
        return RuleResult(
            "D16", "D", "Pas de symboles dans les cellules",
            Status.PASS, Severity.MAJOR, evidence="Aucun symbole détecté",
        )
    return RuleResult(
        "D16", "D", "Pas de symboles dans les cellules",
        Status.FAIL, Severity.MAJOR,
        evidence=f"{bad} cellules contiennent des symboles: {', '.join(samples)}",
        recommendation="Remplacer ✓/✗ par 'oui'/'non' (texte explicite).",
        remediable=True,
    )


@register
def rule_table_pagination(p: ParsedDoc, _: Settings) -> RuleResult:
    if not p.tables:
        return RuleResult(
            "D17", "D", "Pagination/en-têtes répétés sur tableaux longs",
            Status.PASS, Severity.MINOR, evidence="Aucun tableau",
        )
    return RuleResult(
        "D17", "D", "Pagination/en-têtes répétés sur tableaux longs",
        Status.NOT_VERIFIABLE, Severity.MINOR,
        evidence="Non vérifiable automatiquement",
        recommendation="Vérifier manuellement la répétition des en-têtes pour les tableaux multi-pages.",
    )


@register
def rule_table_native(p: ParsedDoc, _: Settings) -> RuleResult:
    text_lower = full_text(p).lower()
    if not p.tables and p.images and "tableau" in text_lower:
        return RuleResult(
            "D18", "D", "Tableau natif (pas une image)",
            Status.FAIL, Severity.BLOCKER,
            evidence=f"{len(p.images)} image(s) + mentions 'tableau' mais aucun tableau natif détecté",
            recommendation="Recréer le tableau au format natif (DOCX/PPTX/XLSX).",
        )
    return RuleResult(
        "D18", "D", "Tableau natif (pas une image)",
        Status.PASS, Severity.BLOCKER,
        evidence=f"{len(p.tables)} tableau(x) natif(s)",
    )
