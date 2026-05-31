"""Catégorie H — Données sensibles (extension KM, BLOQUANT).

Items :
  H28 Aucune donnée client / personnelle (hors auteur) n'est présente
      dans le document.
  H29 Étiquette de confidentialité compatible avec une intégration KM
      (Public ou Interne).

Cette catégorie n'apparaît pas dans la checklist officielle des
normes-connaissances mais elle est imposée par la contrainte
sécurité/data du dispositif KM. Le retour métier précise que H29
peut, à terme, être délégué à SharePoint ; l'implémentation
ci-dessous reste un filet de sécurité au niveau document.
"""
from __future__ import annotations

import re

from ..config import Settings
from ..models import ParsedDoc, RuleResult, Severity, Status
from ..sensitive import detect_sensitive, has_findings, summarize
from . import register
from ._helpers import full_text


_LABEL_TRIGGER_RE = re.compile(
    r"(?i)\b(?:sensibilit[ée]|confidentialit[ée]|classification|sensitivity|label|étiquette|"
    r"information protection)\b"
)
_SAFE_LABEL_RE = re.compile(r"(?i)\b(public|interne|internal)\b")
_RESTRICTED_LABEL_RE = re.compile(
    r"(?i)\b(priv[ée]|private|confidentiel(?:le)?|confidential|secret|restricted|"
    r"restreint(?:e)?|strictement\s+confidentiel)\b"
)


@register
def rule_sensitive_data(p: ParsedDoc, _: Settings) -> RuleResult:
    findings = detect_sensitive(full_text(p))
    if not has_findings(findings):
        return RuleResult(
            "H28", "H",
            "Aucune donnée client / personnelle détectée",
            Status.PASS, Severity.BLOCKER,
            evidence="Aucun pattern sensible détecté",
        )

    # Locate each finding among the text blocks (best effort: first match).
    needles: list[str] = []
    for vals in findings.values():
        needles.extend(vals)
    locations: list[str] = []
    for idx, block in enumerate(p.text_blocks):
        if any(n and n in block for n in needles):
            loc = p.locate(idx)
            if loc:
                locations.append(loc)

    return RuleResult(
        "H28", "H",
        "Aucune donnée client / personnelle détectée",
        Status.FAIL, Severity.BLOCKER,
        evidence=" | ".join(summarize(findings)),
        location="; ".join(dict.fromkeys(locations)),
        recommendation="Anonymiser/retirer toute donnée client/personnelle avant publication.",
        remediable=True,
    )


@register
def rule_sensitivity_label(p: ParsedDoc, _: Settings) -> RuleResult:
    """H29 — étiquette de confidentialité.

    Conformément au retour métier : un document KM doit être étiqueté
    Public ou Interne ; toute autre étiquette (Confidentiel, Secret,
    Privé…) ou l'absence d'étiquette est bloquante. La détection
    s'appuie sur les libellés présents en tête du document
    (head[:4000]). Le retour métier précise qu'à terme, ce contrôle
    pourra être délégué à SharePoint / Microsoft Purview.
    """
    head = full_text(p)[:4000]
    # 1. Étiquette présente et explicitement compatible
    trigger = _LABEL_TRIGGER_RE.search(head)
    if trigger:
        window = head[trigger.start(): trigger.start() + 200]
        if _RESTRICTED_LABEL_RE.search(window):
            label = _RESTRICTED_LABEL_RE.search(window).group(0)
            return RuleResult(
                "H29", "H",
                "Étiquette de confidentialité compatible KM (Public / Interne)",
                Status.FAIL, Severity.BLOCKER,
                evidence=f"Étiquette incompatible détectée : « {label} ».",
                recommendation=(
                    "Reconfigurer l'étiquette en « Public » ou « Interne » "
                    "avant intégration KM."
                ),
            )
        if _SAFE_LABEL_RE.search(window):
            label = _SAFE_LABEL_RE.search(window).group(0)
            return RuleResult(
                "H29", "H",
                "Étiquette de confidentialité compatible KM (Public / Interne)",
                Status.PASS, Severity.BLOCKER,
                evidence=f"Étiquette compatible : « {label} ».",
            )
    # 2. Aucune étiquette détectée → bloquant (retour métier)
    return RuleResult(
        "H29", "H",
        "Étiquette de confidentialité compatible KM (Public / Interne)",
        Status.FAIL, Severity.BLOCKER,
        evidence="Aucune étiquette de confidentialité détectée.",
        recommendation=(
            "Appliquer une étiquette « Public » ou « Interne » via SharePoint / "
            "Microsoft Purview avant intégration KM."
        ),
    )
