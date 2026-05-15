"""Catégorie I — Bonnes pratiques générales (extension, non bloquant).

Items :
  I29 Pas de coupures de mots/paragraphes
  I30 Format DOCX privilégié
  I31 Document de longueur raisonnable
  I32 Pas d'en-têtes/pieds de page superflus
  I33 Phrases courtes et simples
  I34 Alignement à gauche (PPT/PDF)
  I35 Paragraphes ≤ max_paragraph_chars
"""
from __future__ import annotations

import re

from ..config import Settings
from ..models import ParsedDoc, RuleResult, Severity, Status
from . import register
from ._helpers import full_text


@register
def rule_word_breaks(p: ParsedDoc, _: Settings) -> RuleResult:
    breaks = len(re.findall(r"-\s*\n", full_text(p)))
    if breaks <= 2:
        return RuleResult(
            "I29", "I", "Pas de coupures de mots/paragraphes",
            Status.PASS, Severity.MINOR, evidence=f"{breaks} coupures",
        )
    return RuleResult(
        "I29", "I", "Pas de coupures de mots/paragraphes",
        Status.WARN, Severity.MINOR,
        evidence=f"{breaks} coupures détectées",
        recommendation="Désactiver la césure automatique; reflow le texte.",
    )


@register
def rule_format_preference(p: ParsedDoc, _: Settings) -> RuleResult:
    if p.file_type == "docx":
        return RuleResult(
            "I30", "I", "Format DOCX privilégié",
            Status.PASS, Severity.MINOR, evidence="DOCX",
        )
    return RuleResult(
        "I30", "I", "Format DOCX privilégié",
        Status.WARN, Severity.MINOR,
        evidence=f"Format actuel: {p.file_type.upper()}",
        recommendation="Si possible, privilégier DOCX pour la maintenabilité du contenu.",
    )


@register
def rule_doc_length(p: ParsedDoc, settings: Settings) -> RuleResult:
    if p.pages <= settings.long_doc_pages:
        return RuleResult(
            "I31", "I", "Document de longueur raisonnable",
            Status.PASS, Severity.MINOR, evidence=f"{p.pages} pages",
        )
    return RuleResult(
        "I31", "I", "Document de longueur raisonnable",
        Status.WARN, Severity.MINOR,
        evidence=f"{p.pages} pages (> {settings.long_doc_pages})",
        recommendation="Si possible, découper le document en plusieurs livrables thématiques.",
    )


@register
def rule_headers_footers(p: ParsedDoc, _: Settings) -> RuleResult:
    if p.file_type != "docx":
        return RuleResult(
            "I32", "I", "Pas d'en-têtes/pieds de page superflus",
            Status.NOT_VERIFIABLE, Severity.MINOR,
        )
    if p.extra.get("has_headers_footers"):
        return RuleResult(
            "I32", "I", "Pas d'en-têtes/pieds de page superflus",
            Status.WARN, Severity.MINOR,
            evidence="En-tête/pied détecté",
            recommendation="Limiter les en-têtes/pieds de page (réduisent la lisibilité IA).",
        )
    return RuleResult(
        "I32", "I", "Pas d'en-têtes/pieds de page superflus",
        Status.PASS, Severity.MINOR,
    )


@register
def rule_short_sentences(p: ParsedDoc, settings: Settings) -> RuleResult:
    text = full_text(p)
    sentences = re.split(r"[\.\!\?]\s+", text)
    word_counts = [len(s.split()) for s in sentences if s.strip()]
    if not word_counts:
        return RuleResult(
            "I33", "I", "Phrases courtes et simples",
            Status.NOT_VERIFIABLE, Severity.MINOR, evidence="Pas de texte",
        )
    avg = sum(word_counts) / len(word_counts)
    if avg <= settings.max_avg_sentence_words:
        return RuleResult(
            "I33", "I", "Phrases courtes et simples",
            Status.PASS, Severity.MINOR,
            evidence=f"Moyenne {avg:.1f} mots/phrase",
        )
    return RuleResult(
        "I33", "I", "Phrases courtes et simples",
        Status.WARN, Severity.MINOR,
        evidence=f"Moyenne {avg:.1f} mots/phrase (> {settings.max_avg_sentence_words})",
        recommendation="Raccourcir les phrases (cible: 15-20 mots).",
    )


@register
def rule_max_paragraph_length(p: ParsedDoc, settings: Settings) -> RuleResult:
    too_long = [t for t in p.text_blocks if len(t) > settings.max_paragraph_chars]
    if not too_long:
        return RuleResult(
            "I35", "I", "Paragraphes de longueur raisonnable",
            Status.PASS, Severity.MINOR,
            evidence=f"Aucun paragraphe > {settings.max_paragraph_chars} chars",
        )
    return RuleResult(
        "I35", "I", "Paragraphes de longueur raisonnable",
        Status.WARN, Severity.MINOR,
        evidence=(
            f"{len(too_long)} paragraphe(s) > {settings.max_paragraph_chars} chars "
            f"(max observé: {max(len(t) for t in too_long)})"
        ),
        recommendation="Découper les paragraphes longs en blocs courts pour faciliter la recherche par l'outil.",
    )


@register
def rule_left_alignment(p: ParsedDoc, _: Settings) -> RuleResult:
    if p.file_type not in {"pptx", "pdf"}:
        return RuleResult(
            "I34", "I", "Alignement à gauche (PPT/PDF)",
            Status.NOT_VERIFIABLE, Severity.MINOR,
        )
    multiple_spaces = len(re.findall(r"  {2,}", full_text(p)))
    if multiple_spaces > 20:
        return RuleResult(
            "I34", "I", "Alignement à gauche (PPT/PDF)",
            Status.WARN, Severity.MINOR,
            evidence=f"{multiple_spaces} séquences d'espaces multiples (potentiellement justifié/centré)",
            recommendation="Privilégier un alignement à gauche pour une meilleure lisibilité.",
        )
    return RuleResult(
        "I34", "I", "Alignement à gauche (PPT/PDF)",
        Status.PASS, Severity.MINOR,
    )
