"""Category A – Document identification (BLOCKER)."""
from __future__ import annotations

import re

from ..config import (
    ACRONYM_RE,
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
            "A1", "A", "Nommage du fichier (AAAAMMJJ_Sujet_Type_Extra.ext)",
            Status.PASS, Severity.BLOCKER, evidence=p.file_name,
        )
    return RuleResult(
        "A1", "A", "Nommage du fichier (AAAAMMJJ_Sujet_Type_Extra.ext)",
        Status.FAIL, Severity.BLOCKER, evidence=p.file_name,
        recommendation=(
            "Renommer au format AAAAMMJJ_Sujet_TypeDeDocument(_Infos).ext, "
            "ex: 20260121_Guidelines_KM_Cash.pptx"
        ),
        remediable=True,
    )


@register
def rule_cartouche(p: ParsedDoc, _: Settings) -> RuleResult:
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
            "A2", "A", "Cartouche renseigné (champs obligatoires)",
            Status.PASS, Severity.BLOCKER, evidence=", ".join(found),
        )
    if len(found) >= 4:
        return RuleResult(
            "A2", "A", "Cartouche renseigné (champs obligatoires)",
            Status.FAIL, Severity.BLOCKER,
            evidence=f"Détectés: {', '.join(found)} | Manquants: {', '.join(missing)}",
            recommendation="Ajouter les champs manquants dans la section Cartouche.",
            remediable=True,
        )
    return RuleResult(
        "A2", "A", "Cartouche renseigné (champs obligatoires)",
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
            "A3", "A", "Objectif/description en début de document",
            Status.PASS, Severity.BLOCKER,
            evidence="Section objectif/description détectée",
        )
    return RuleResult(
        "A3", "A", "Objectif/description en début de document",
        Status.FAIL, Severity.BLOCKER,
        recommendation="Ajouter une section Objectif/Description dans les premières pages.",
        remediable=True,
    )


@register
def rule_acronyms(p: ParsedDoc, _: Settings) -> RuleResult:
    text = full_text(p)
    candidates = {
        a for a in ACRONYM_RE.findall(text)
        if a not in {"PDF", "DOCX", "PPTX", "XLSX"}
    }
    if not candidates:
        return RuleResult(
            "A4", "A", "Acronymes développés à la 1re occurrence",
            Status.PASS, Severity.BLOCKER, evidence="Aucun acronyme détecté",
        )
    undocumented = []
    for ac in candidates:
        first = re.search(rf"\b{re.escape(ac)}\b", text)
        if not first:
            continue
        window = text[max(0, first.start() - 80): first.start() + 200]
        if not (
            re.search(rf"{ac}\s*\(([^)]+)\)", window)
            or re.search(rf"{ac}\s*[:\-–]\s*[A-Za-zÀ-ÿ]", window)
            or re.search(rf"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\s\-]{{2,}}\s*\(\s*{ac}\s*\)", window)
        ):
            undocumented.append(ac)
    if not undocumented:
        return RuleResult(
            "A4", "A", "Acronymes développés à la 1re occurrence",
            Status.PASS, Severity.BLOCKER,
            evidence=f"{len(candidates)} acronymes détectés, tous documentés",
        )
    return RuleResult(
        "A4", "A", "Acronymes développés à la 1re occurrence",
        Status.FAIL, Severity.BLOCKER,
        evidence=f"Non développés: {', '.join(sorted(undocumented)[:15])}",
        recommendation="Développer chaque acronyme à sa première occurrence: ACR (Définition).",
    )


@register
def rule_glossary(p: ParsedDoc, _: Settings) -> RuleResult:
    text = full_text(p).lower()
    if any(h in text for h in GLOSSARY_HINTS):
        return RuleResult(
            "A5", "A", "Glossaire / liste d'acronymes présent",
            Status.PASS, Severity.BLOCKER,
            evidence="Section glossaire/acronymes détectée",
        )
    return RuleResult(
        "A5", "A", "Glossaire / liste d'acronymes présent",
        Status.FAIL, Severity.BLOCKER,
        recommendation="Ajouter une section Glossaire en fin de document.",
        remediable=True,
    )
