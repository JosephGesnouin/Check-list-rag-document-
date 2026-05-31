"""Catégorie A — Permettre l'identification du document.

À la suite du retour métier, seule la règle A1 (nom de fichier) est
conservée. Les contrôles A2 (cartouche), A3 (objectif dans les
métadonnées) et A4 (glossaire centralisé) sont désormais assurés
par l'interface Domino : ils ont donc été retirés du périmètre de
l'audit automatique.

Les générateurs ``inject_cartouche``, ``inject_objective`` et
``inject_glossary`` restent disponibles dans le moteur de remédiation
pour les utilisateurs qui souhaitent les invoquer manuellement, mais
``build_plan`` ne les ajoute plus automatiquement.
"""
from __future__ import annotations

from ..config import NAMING_REGEX, Settings
from ..models import ParsedDoc, RuleResult, Severity, Status
from . import register


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
