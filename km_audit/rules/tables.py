"""Catégorie E — Gestion des tableaux.

Items officiels (8) :
  E12 Le tableau évite-t-il toute cellule fusionnée ?
  E13 Les bordures sont-elles visibles (idéalement noires sur fond blanc) ?
  E14 Les en-têtes de colonnes sont-ils clairs et mis en valeur ?
  E15 Un titre explicite est-il présent au-dessus du tableau ?
  E16 Le tableau est-il accompagné d'une légende qui décrit le contenu ?
  E17 Les symboles / codes couleurs remplacés par des mots clairs ?
  E18 Pagination / en-têtes répétés sur plusieurs pages ?
  E19 Tableau au format natif (pas image / capture) ?
"""
from __future__ import annotations

from ..config import EMOJI_OR_SYMBOL_RE, Settings
from ..models import ParsedDoc, RuleResult, Severity, Status
from . import register
from ._helpers import full_text, truncate


@register
def rule_table_no_merge(p: ParsedDoc, _: Settings) -> RuleResult:
    if not p.tables:
        return RuleResult(
            "E12", "E", "Pas de cellules fusionnées",
            Status.PASS, Severity.MAJOR, evidence="Aucun tableau",
        )
    merged = [t for t in p.tables if t.get("merged")]
    if not merged:
        return RuleResult(
            "E12", "E", "Pas de cellules fusionnées",
            Status.PASS, Severity.MAJOR,
            evidence=f"{len(p.tables)} tableau(x) sans fusion",
        )
    return RuleResult(
        "E12", "E", "Pas de cellules fusionnées",
        Status.WARN, Severity.MAJOR,
        evidence=f"{len(merged)} tableau(x) avec cellules fusionnées",
        recommendation="Dé-fusionner les cellules pour permettre une lecture machine.",
    )


@register
def rule_table_borders(p: ParsedDoc, _: Settings) -> RuleResult:
    if not p.tables:
        return RuleResult(
            "E13", "E", "Bordures visibles (idéalement noires sur fond blanc)",
            Status.PASS, Severity.MINOR, evidence="Aucun tableau",
        )
    if p.file_type != "xlsx":
        return RuleResult(
            "E13", "E", "Bordures visibles (idéalement noires sur fond blanc)",
            Status.NOT_VERIFIABLE, Severity.MINOR,
            evidence="Vérification automatique limitée hors XLSX",
        )
    no_border = [t for t in p.tables if not t.get("borders")]
    if not no_border:
        return RuleResult(
            "E13", "E", "Bordures visibles (idéalement noires sur fond blanc)",
            Status.PASS, Severity.MAJOR,
            evidence="Bordures détectées sur toutes les feuilles",
        )
    return RuleResult(
        "E13", "E", "Bordures visibles (idéalement noires sur fond blanc)",
        Status.WARN, Severity.MAJOR,
        evidence=f"{len(no_border)} feuille(s) sans bordure détectée",
        recommendation="Appliquer des bordures noires fines sur les tableaux.",
    )


@register
def rule_table_headers(p: ParsedDoc, _: Settings) -> RuleResult:
    if not p.tables:
        return RuleResult(
            "E14", "E", "En-têtes de colonnes clairs et mis en valeur",
            Status.PASS, Severity.MAJOR, evidence="Aucun tableau",
        )
    weak = [t for t in p.tables if not t.get("header_bold")]
    if not weak:
        return RuleResult(
            "E14", "E", "En-têtes de colonnes clairs et mis en valeur",
            Status.PASS, Severity.MAJOR,
            evidence="Première ligne en gras pour tous les tableaux",
        )
    return RuleResult(
        "E14", "E", "En-têtes de colonnes clairs et mis en valeur",
        Status.WARN, Severity.MAJOR,
        evidence=f"{len(weak)} tableau(x) sans en-tête en gras",
        recommendation="Mettre la première ligne en gras et/ou utiliser un fond distinct.",
    )


@register
def rule_table_title(p: ParsedDoc, _: Settings) -> RuleResult:
    if not p.tables:
        return RuleResult(
            "E15", "E", "Titre explicite au-dessus du tableau",
            Status.PASS, Severity.MAJOR, evidence="Aucun tableau",
        )
    text = full_text(p).lower()
    titles = text.count("tableau")
    if titles >= len(p.tables):
        return RuleResult(
            "E15", "E", "Titre explicite au-dessus du tableau",
            Status.PASS, Severity.MAJOR,
            evidence=f"{titles} mentions 'Tableau' / {len(p.tables)} tableaux",
        )
    return RuleResult(
        "E15", "E", "Titre explicite au-dessus du tableau",
        Status.WARN, Severity.MAJOR,
        evidence=f"{titles} mentions 'Tableau' / {len(p.tables)} tableaux",
        recommendation="Préfixer chaque tableau d'un intitulé 'Tableau X – ...'.",
    )


@register
def rule_table_caption(p: ParsedDoc, _: Settings) -> RuleResult:
    if not p.tables:
        return RuleResult(
            "E16", "E", "Légende décrivant le contenu du tableau",
            Status.PASS, Severity.MAJOR, evidence="Aucun tableau",
        )
    text = full_text(p).lower()
    captions = sum(text.count(h) for h in ("légende", "ce tableau", "ce tableau présente",
                                           "description :", "description du tableau"))
    if captions >= len(p.tables):
        return RuleResult(
            "E16", "E", "Légende décrivant le contenu du tableau",
            Status.PASS, Severity.MAJOR,
            evidence=f"{captions} mentions de légende / {len(p.tables)} tableaux",
        )
    return RuleResult(
        "E16", "E", "Légende décrivant le contenu du tableau",
        Status.WARN, Severity.MAJOR,
        evidence=f"{captions} mentions de légende / {len(p.tables)} tableaux",
        recommendation="Compléter chaque tableau par une phrase descriptive (légende).",
    )


@register
def rule_table_symbols(p: ParsedDoc, _: Settings) -> RuleResult:
    if not p.tables:
        return RuleResult(
            "E17", "E", "Symboles / codes couleurs remplacés par des mots",
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
            "E17", "E", "Symboles / codes couleurs remplacés par des mots",
            Status.PASS, Severity.MAJOR, evidence="Aucun symbole détecté",
        )
    return RuleResult(
        "E17", "E", "Symboles / codes couleurs remplacés par des mots",
        Status.FAIL, Severity.MAJOR,
        evidence=f"{bad} cellules contiennent des symboles: {', '.join(samples)}",
        recommendation="Remplacer ✓/✗ par 'oui'/'non' (texte explicite).",
        remediable=True,
    )


@register
def rule_table_pagination(p: ParsedDoc, _: Settings) -> RuleResult:
    if not p.tables:
        return RuleResult(
            "E18", "E", "Pagination / en-têtes répétés sur plusieurs pages",
            Status.PASS, Severity.MINOR, evidence="Aucun tableau",
        )
    return RuleResult(
        "E18", "E", "Pagination / en-têtes répétés sur plusieurs pages",
        Status.NOT_VERIFIABLE, Severity.MINOR,
        evidence="Non vérifiable automatiquement",
        recommendation="Vérifier manuellement la répétition des en-têtes pour les tableaux multi-pages.",
    )


@register
def rule_table_native(p: ParsedDoc, _: Settings) -> RuleResult:
    text_lower = full_text(p).lower()
    if not p.tables and p.images and "tableau" in text_lower:
        return RuleResult(
            "E19", "E", "Tableau au format natif (pas image / capture)",
            Status.WARN, Severity.MAJOR,
            evidence=f"{len(p.images)} image(s) + mentions 'tableau' mais aucun tableau natif détecté",
            recommendation="Recréer le tableau au format natif (DOCX/PPTX/XLSX).",
        )
    return RuleResult(
        "E19", "E", "Tableau au format natif (pas image / capture)",
        Status.PASS, Severity.MAJOR,
        evidence=f"{len(p.tables)} tableau(x) natif(s)",
    )
