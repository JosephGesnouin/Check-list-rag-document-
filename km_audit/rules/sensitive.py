"""Catégorie H — Données sensibles (extension KM, BLOQUANT).

Item :
  H28 Aucune donnée client / personnelle (hors auteur) n'est présente
      dans le document.

Cette catégorie n'apparaît pas dans la checklist officielle des
normes-connaissances mais elle est imposée par la contrainte
sécurité/data du dispositif KM.
"""
from __future__ import annotations

from ..config import Settings
from ..models import ParsedDoc, RuleResult, Severity, Status
from ..sensitive import detect_sensitive, has_findings, summarize
from . import register
from ._helpers import full_text


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
    return RuleResult(
        "H28", "H",
        "Aucune donnée client / personnelle détectée",
        Status.FAIL, Severity.BLOCKER,
        evidence=" | ".join(summarize(findings)),
        recommendation="Anonymiser/retirer toute donnée client/personnelle avant publication KM.",
        remediable=True,
    )
