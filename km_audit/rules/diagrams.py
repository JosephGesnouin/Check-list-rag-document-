"""Catégorie F — Gestion des diagrammes / schémas.

S'applique à tous les formats (DOCX, PPTX, XLSX, PDF). Pour les
formats qui n'exposent pas la structure shapes/boîtes (DOCX, XLSX,
PDF), les contrôles F21–F24 restent en N/V avec un message clair
demandant une revue manuelle ; F20 (libellés génériques) est, lui,
purement textuel et reste vérifiable partout.

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


_PPTX_DETECTABLE = "Heuristique shapes réservée aux PPTX"
_DOCX_MANUAL = "À vérifier manuellement (pas d'extraction shapes pour ce format)"


def _shape_counts(p: ParsedDoc):
    return p.extra.get("diagram_shape_counts", []) if p.file_type == "pptx" else []


@register
def rule_diagram_labels(p: ParsedDoc, _: Settings) -> RuleResult:
    """F20 — libellés génériques. Vérifiable sur tout texte."""
    text = full_text(p).lower()
    if not text.strip():
        return RuleResult(
            "F20", "F", "Éléments des diagrammes nommés précisément",
            Status.NOT_VERIFIABLE, Severity.MINOR,
            evidence="Pas de texte extractible",
        )
    generic = re.findall(r"\b(?:étape|step|phase)\s*\d+\b", text)
    if not generic:
        return RuleResult(
            "F20", "F", "Éléments des diagrammes nommés précisément",
            Status.PASS, Severity.MINOR,
            evidence="Aucun libellé générique détecté",
        )
    return RuleResult(
        "F20", "F", "Éléments des diagrammes nommés précisément",
        Status.WARN, Severity.MINOR,
        evidence=f"Libellés génériques détectés ({len(generic)}) : ex. {', '.join(set(generic[:5]))}",
        recommendation="Renommer les éléments avec des intitulés métier précis.",
    )


@register
def rule_diagram_density(p: ParsedDoc, _: Settings) -> RuleResult:
    """F21 — surcharge visuelle. Heuristique PPTX, sinon revue manuelle."""
    if p.file_type != "pptx":
        return RuleResult(
            "F21", "F", "Structures allégées (pas de surcharge)",
            Status.NOT_VERIFIABLE, Severity.MINOR,
            evidence=_DOCX_MANUAL,
            recommendation="Vérifier visuellement que les diagrammes ne contiennent pas trop de boîtes / flèches croisées.",
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
    """F22 — découpage en sous-diagrammes."""
    if p.file_type != "pptx":
        return RuleResult(
            "F22", "F", "Diagrammes découpés en sous-diagrammes thématiques",
            Status.NOT_VERIFIABLE, Severity.MINOR,
            evidence=_DOCX_MANUAL,
            recommendation="Si un diagramme est très dense, le découper en plusieurs sous-diagrammes thématiques.",
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
    """F23 — alternative texte structuré."""
    if p.file_type != "pptx":
        return RuleResult(
            "F23", "F", "Texte structuré privilégié si plus accessible",
            Status.NOT_VERIFIABLE, Severity.MINOR,
            evidence=_DOCX_MANUAL,
            recommendation="Pour les schémas complexes, proposer un texte structuré équivalent dans le document.",
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
    """F24 — légende explicative. Heuristique texte universelle."""
    text = full_text(p).lower()
    has_diagram_hint = any(h in text for h in ("schéma", "schema", "diagramme", "figure"))
    captions = sum(text.count(h) for h in ("légende", "logique", "ce schéma", "ce diagramme"))
    if p.file_type == "pptx":
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
    # Autres formats : on ne sait pas combien il y a de diagrammes, on
    # se contente de signaler la présence (ou non) de légendes.
    if not has_diagram_hint:
        return RuleResult(
            "F24", "F", "Légende explicative décrivant la logique",
            Status.PASS, Severity.MINOR,
            evidence="Aucun mot-clé diagramme/schéma détecté",
        )
    if captions > 0:
        return RuleResult(
            "F24", "F", "Légende explicative décrivant la logique",
            Status.PASS, Severity.MINOR,
            evidence=f"{captions} mention(s) de légende repérée(s)",
        )
    return RuleResult(
        "F24", "F", "Légende explicative décrivant la logique",
        Status.WARN, Severity.MINOR,
        evidence="Schémas/diagrammes mentionnés mais aucune légende détectée",
        recommendation="Ajouter une légende textuelle décrivant la logique de chaque diagramme.",
    )
