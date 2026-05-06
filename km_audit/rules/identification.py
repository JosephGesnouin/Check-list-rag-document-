"""Catégorie A — Permettre l'identification du document (BLOQUANT).

Items officiels :
  A1  Le nom du document suit-il la norme de nommage ?
  A2  Les informations du document (cartouche/métadonnées) sont-elles renseignées ?
  A3  Y a-t-il une description claire de l'objectif dans les métadonnées ?
  A4  Les acronymes / termes spécialisés présents ont-ils été ajoutés
      (ou vérifiés) dans le glossaire de domaine centralisé ?
"""
from __future__ import annotations

import re

from ..config import (
    GLOSSARY_HINTS,
    NAMING_REGEX,
    OBJECTIVE_HINTS,
    REQUIRED_CARTOUCHE_FIELDS,
    Settings,
)
from ..models import ParsedDoc, RuleResult, Severity, Status
from . import register
from ._helpers import full_text


@register
def rule_naming(p: ParsedDoc, _: Settings) -> RuleResult:
    if NAMING_REGEX.match(p.file_name):
        return RuleResult(
            "A1", "A",
            "Nom du document conforme (AAAAMMJJ_Sujet_Type_Infos)",
            Status.PASS, Severity.BLOCKER, evidence=p.file_name,
        )
    return RuleResult(
        "A1", "A",
        "Nom du document conforme (AAAAMMJJ_Sujet_Type_Infos)",
        Status.FAIL, Severity.BLOCKER, evidence=p.file_name,
        recommendation=(
            "Renommer au format AAAAMMJJ_Sujet_TypeDeDocument(_Infos).ext, "
            "ex: 20260121_Guidelines_KM_Cash.pptx"
        ),
        remediable=True,
    )


@register
def rule_metadata(p: ParsedDoc, _: Settings) -> RuleResult:
    text = full_text(p)
    head = text[:4000]
    found, missing = [], []
    for label in REQUIRED_CARTOUCHE_FIELDS:
        if re.search(rf"\b{re.escape(label)}", head, re.IGNORECASE):
            found.append(label)
        else:
            missing.append(label)
    props = p.extra.get("xlsx_props") if p.file_type == "xlsx" else None
    if props:
        if props.get("creator") and "Auteur" in missing:
            missing.remove("Auteur")
            found.append("Auteur (xlsx props)")
        if props.get("keywords") and "Mot" in missing:
            missing.remove("Mot")
            found.append("Mots clés (xlsx props)")

    if not missing:
        return RuleResult(
            "A2", "A", "Informations du document renseignées (cartouche / métadonnées)",
            Status.PASS, Severity.BLOCKER, evidence=", ".join(found),
        )
    if len(found) >= 4:
        return RuleResult(
            "A2", "A", "Informations du document renseignées (cartouche / métadonnées)",
            Status.FAIL, Severity.BLOCKER,
            evidence=f"Détectés: {', '.join(found)} | Manquants: {', '.join(missing)}",
            recommendation="Ajouter les champs manquants dans la section Cartouche.",
            remediable=True,
        )
    return RuleResult(
        "A2", "A", "Informations du document renseignées (cartouche / métadonnées)",
        Status.NOT_VERIFIABLE, Severity.BLOCKER,
        evidence="Cartouche non détecté automatiquement.",
        recommendation="Vérifier manuellement la présence d'un cartouche conforme.",
        remediable=True,
    )


@register
def rule_objective(p: ParsedDoc, _: Settings) -> RuleResult:
    head = full_text(p)[:3000].lower()
    if any(h in head for h in OBJECTIVE_HINTS):
        return RuleResult(
            "A3", "A",
            "Description claire de l'objectif dans les métadonnées",
            Status.PASS, Severity.BLOCKER,
            evidence="Section objectif/description détectée",
        )
    return RuleResult(
        "A3", "A",
        "Description claire de l'objectif dans les métadonnées",
        Status.FAIL, Severity.BLOCKER,
        recommendation="Ajouter une section Objectif/Description dans les métadonnées ou en tête.",
        remediable=True,
    )


@register
def rule_glossary(p: ParsedDoc, _: Settings) -> RuleResult:
    text = full_text(p).lower()
    if any(h in text for h in GLOSSARY_HINTS):
        return RuleResult(
            "A4", "A",
            "Acronymes/termes ajoutés (ou vérifiés) au glossaire centralisé",
            Status.PASS, Severity.BLOCKER,
            evidence="Section glossaire/acronymes détectée",
        )
    return RuleResult(
        "A4", "A",
        "Acronymes/termes ajoutés (ou vérifiés) au glossaire centralisé",
        Status.FAIL, Severity.BLOCKER,
        recommendation="Ajouter une section Glossaire centralisée en fin de document.",
        remediable=True,
    )
