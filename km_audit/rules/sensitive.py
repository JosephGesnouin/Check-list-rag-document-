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
