"""Catégorie C — Mise en forme du texte (BLOQUANT).

Items officiels :
  C7  Les acronymes ou abréviations sont-ils expliqués / développés
      à leur première apparition ?
  C8  Le texte évite-t-il d'être inséré dans des boîtes ou cadres
      (textbox) inutiles ?
  C9  Le document évite-t-il l'usage de logos, symboles ou icônes
      dans les phrases ?
"""
from __future__ import annotations

import re

from ..config import ACRONYM_RE, EMOJI_OR_SYMBOL_RE, Settings
from ..models import ParsedDoc, RuleResult, Severity, Status
from . import register
from ._helpers import full_text, truncate


@register
def rule_acronyms_first_occurrence(p: ParsedDoc, _: Settings) -> RuleResult:
    text = full_text(p)
    candidates = {
        a for a in ACRONYM_RE.findall(text)
        if a not in {"PDF", "DOCX", "PPTX", "XLSX"}
    }
    if not candidates:
        return RuleResult(
            "C7", "C", "Acronymes/abréviations expliqués à leur 1re apparition",
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
            "C7", "C", "Acronymes/abréviations expliqués à leur 1re apparition",
            Status.PASS, Severity.BLOCKER,
            evidence=f"{len(candidates)} acronymes détectés, tous documentés",
        )
    return RuleResult(
        "C7", "C", "Acronymes/abréviations expliqués à leur 1re apparition",
        Status.FAIL, Severity.BLOCKER,
        evidence=f"Non développés: {', '.join(sorted(undocumented)[:15])}",
        recommendation="Développer chaque acronyme à sa première occurrence: ACR (Définition).",
    )


@register
def rule_textboxes(p: ParsedDoc, _: Settings) -> RuleResult:
    if p.file_type == "pptx":
        n = p.extra.get("standalone_textboxes", 0)
        if n <= 2:
            return RuleResult(
                "C8", "C", "Texte hors boîtes/cadres (textbox) inutiles",
                Status.PASS, Severity.BLOCKER, evidence=f"{n} textbox(es) hors titre",
            )
        return RuleResult(
            "C8", "C", "Texte hors boîtes/cadres (textbox) inutiles",
            Status.FAIL, Severity.BLOCKER,
            evidence=f"{n} textbox(es) hors titre détectés",
            recommendation="Limiter les zones de texte flottantes; privilégier les placeholders.",
        )
    return RuleResult(
        "C8", "C", "Texte hors boîtes/cadres (textbox) inutiles",
        Status.NOT_VERIFIABLE, Severity.MAJOR,
        evidence="Détection automatique limitée hors PPTX",
    )


@register
def rule_no_symbols_in_sentences(p: ParsedDoc, _: Settings) -> RuleResult:
    offenders = []
    locations = []
    for idx, block in enumerate(p.text_blocks):
        loc = p.locate(idx)
        for line in block.splitlines():
            if EMOJI_OR_SYMBOL_RE.search(line) and len(line.split()) >= 4:
                offenders.append(truncate(line, 120))
                if loc:
                    locations.append(loc)
                if len(offenders) >= 5:
                    break
        if len(offenders) >= 5:
            break
    if not offenders:
        return RuleResult(
            "C9", "C", "Pas de logos/symboles/icônes dans les phrases",
            Status.PASS, Severity.BLOCKER,
        )
    return RuleResult(
        "C9", "C", "Pas de logos/symboles/icônes dans les phrases",
        Status.FAIL, Severity.BLOCKER,
        evidence=" | ".join(offenders),
        location="; ".join(dict.fromkeys(locations)),
        recommendation="Remplacer les symboles (✓, ➜, etc.) par des mots équivalents.",
        remediable=True,
    )
