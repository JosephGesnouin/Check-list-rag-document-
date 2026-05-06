"""Catégorie F — Gestion des diagrammes / schémas.

Items officiels (5) :
  F20 Les éléments des diagrammes / schémas sont-ils nommés de manière
      précise et descriptive (éviter les intitulés génériques type « Étape 1 ») ?
  F21 Les structures sont-elles allégées (pas de flèches croisées,
      nombre de boîtes limité) ?
  F22 Les diagrammes sont-ils découpés en sous-diagrammes thématiques
      si nécessaire ?
  F23 Les diagrammes ont-ils été remplacés par du texte structuré
      lorsque cela rend l'information plus accessible ?
  F24 Une légende explicite décrit-elle la logique du diagramme ?
"""
from __future__ import annotations

import re

from ..config import Settings
from ..models import ParsedDoc, RuleResult, Severity, Status
from . import register
from ._helpers import full_text


def _shape_counts(p: ParsedDoc):
    return p.extra.get("diagram_shape_counts", []) if p.file_type == "pptx" else []


def _is_pptx_or_pdf(p: ParsedDoc) -> bool:
    return p.file_type in {"pptx", "pdf"}


@register
def rule_diagram_labels(p: ParsedDoc, _: Settings) -> RuleResult:
    if p.file_type != "pptx":
        return RuleResult(
            "F20", "F", "Éléments des diagrammes nommés précisément",
            Status.NOT_VERIFIABLE, Severity.MINOR,
            evidence="Heuristique réservée aux PPTX",
        )
    text = full_text(p).lower()
    generic = bool(re.search(r"\bétape\s*\d|\bstep\s*\d|\bphase\s*\d", text))
    if not generic:
        return RuleResult(
            "F20", "F", "Éléments des diagrammes nommés précisément",
            Status.PASS, Severity.MINOR, evidence="Aucun libellé générique détecté",
        )
    return RuleResult(
        "F20", "F", "Éléments des diagrammes nommés précisément",
        Status.WARN, Severity.MINOR,
        evidence="Libellés génériques détectés (Étape N / Step N / Phase N)",
        recommendation="Renommer les éléments avec des intitulés métier précis.",
    )


@register
def rule_diagram_density(p: ParsedDoc, _: Settings) -> RuleResult:
    if p.file_type != "pptx":
        return RuleResult(
            "F21", "F", "Structures allégées (pas de surcharge)",
            Status.NOT_VERIFIABLE, Severity.MINOR,
            evidence="Heuristique réservée aux PPTX",
        )
    counts = _shape_counts(p)
    overloaded = [c for c in counts if c >= 15]
    if not overloaded:
        return RuleResult(
            "F21", "F", "Structures allégées (pas de surcharge)",
            Status.PASS, Severity.MINOR,
            evidence=f"Aucun slide > 15 shapes ({len(counts)} slides analysés)",
        )
    return RuleResult(
        "F21", "F", "Structures allégées (pas de surcharge)",
        Status.WARN, Severity.MINOR,
        evidence=f"{len(overloaded)} slide(s) avec ≥ 15 shapes",
        recommendation="Limiter le nombre de boîtes/flèches; éviter les flèches croisées.",
    )


@register
def rule_diagram_split(p: ParsedDoc, _: Settings) -> RuleResult:
    if p.file_type != "pptx":
        return RuleResult(
            "F22", "F", "Diagrammes découpés en sous-diagrammes thématiques",
            Status.NOT_VERIFIABLE, Severity.MINOR,
            evidence="Heuristique réservée aux PPTX",
        )
    counts = _shape_counts(p)
    very_dense = [c for c in counts if c >= 25]
    if not very_dense:
        return RuleResult(
            "F22", "F", "Diagrammes découpés en sous-diagrammes thématiques",
            Status.PASS, Severity.MINOR,
            evidence="Aucun slide hyper-dense (≥ 25 shapes)",
        )
    return RuleResult(
        "F22", "F", "Diagrammes découpés en sous-diagrammes thématiques",
        Status.WARN, Severity.MINOR,
        evidence=f"{len(very_dense)} slide(s) avec ≥ 25 shapes",
        recommendation="Découper les diagrammes denses en sous-diagrammes thématiques.",
    )


@register
def rule_diagram_text_alternative(p: ParsedDoc, _: Settings) -> RuleResult:
    if p.file_type != "pptx":
        return RuleResult(
            "F23", "F", "Texte structuré privilégié si plus accessible",
            Status.NOT_VERIFIABLE, Severity.MINOR,
            evidence="Heuristique réservée aux PPTX",
        )
    counts = _shape_counts(p)
    suspect = [c for c in counts if c >= 20]
    if not suspect:
        return RuleResult(
            "F23", "F", "Texte structuré privilégié si plus accessible",
            Status.PASS, Severity.MINOR,
            evidence="Aucun diagramme dense candidat à un texte alternatif",
        )
    return RuleResult(
        "F23", "F", "Texte structuré privilégié si plus accessible",
        Status.WARN, Severity.MINOR,
        evidence=f"{len(suspect)} slide(s) ≥ 20 shapes — envisager un format texte",
        recommendation="Quand un diagramme reste dense, proposer un texte structuré équivalent.",
    )


@register
def rule_diagram_caption(p: ParsedDoc, _: Settings) -> RuleResult:
    if p.file_type != "pptx":
        return RuleResult(
            "F24", "F", "Légende explicative décrivant la logique",
            Status.NOT_VERIFIABLE, Severity.MINOR,
            evidence="Heuristique réservée aux PPTX",
        )
    text = full_text(p).lower()
    captions = sum(text.count(h) for h in ("schéma", "diagramme", "logique", "légende"))
    counts = _shape_counts(p)
    diagram_slides = sum(1 for c in counts if c >= 8)
    if diagram_slides == 0 or captions >= diagram_slides:
        return RuleResult(
            "F24", "F", "Légende explicative décrivant la logique",
            Status.PASS, Severity.MINOR,
            evidence=f"{captions} mentions de légende / {diagram_slides} slides à diagramme",
        )
    return RuleResult(
        "F24", "F", "Légende explicative décrivant la logique",
        Status.WARN, Severity.MINOR,
        evidence=f"{captions} mentions de légende / {diagram_slides} slides à diagramme",
        recommendation="Ajouter une légende textuelle explicitant la logique de chaque diagramme.",
    )
