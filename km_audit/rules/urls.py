"""Category F – URLs."""
from __future__ import annotations

from typing import List, Tuple

from ..config import TRACKING_PARAMS, URL_RE, Settings
from ..models import ParsedDoc, RuleResult, Severity, Status
from . import register
from ._helpers import truncate


def clean_url(url: str) -> Tuple[str, List[str]]:
    """Return (cleaned_url, dropped_params)."""
    if "?" not in url:
        return url, []
    base, qs = url.split("?", 1)
    keep, drop = [], []
    for part in qs.split("&"):
        if any(part.lower().startswith(t) for t in TRACKING_PARAMS):
            drop.append(part)
        else:
            keep.append(part)
    cleaned = base + ("?" + "&".join(keep) if keep else "")
    return cleaned, drop


@register
def rule_url_context(p: ParsedDoc, _: Settings) -> RuleResult:
    if not p.urls:
        return RuleResult(
            "F25", "F", "URLs introduites par un texte de contexte",
            Status.PASS, Severity.MAJOR, evidence="Aucune URL",
        )
    bad = []
    for block in p.text_blocks:
        for line in block.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            m = URL_RE.match(stripped)
            if m and (m.end() - m.start()) >= len(stripped) - 5:
                bad.append(truncate(stripped, 80))
    if not bad:
        return RuleResult(
            "F25", "F", "URLs introduites par un texte de contexte",
            Status.PASS, Severity.MAJOR,
            evidence=f"{len(p.urls)} URL(s) avec contexte",
        )
    return RuleResult(
        "F25", "F", "URLs introduites par un texte de contexte",
        Status.FAIL, Severity.MAJOR,
        evidence=f"URL(s) seule(s) sur ligne: {', '.join(bad[:3])}",
        recommendation="Précéder chaque URL d'un texte d'introduction explicite.",
    )


@register
def rule_url_clean(p: ParsedDoc, _: Settings) -> RuleResult:
    if not p.urls:
        return RuleResult(
            "F26", "F", "URLs nettoyées (pas de tracking)",
            Status.PASS, Severity.MAJOR, evidence="Aucune URL",
        )
    dirty = []
    for u in p.urls:
        cleaned, drop = clean_url(u)
        if drop:
            dirty.append((u, cleaned, drop))
    if not dirty:
        return RuleResult(
            "F26", "F", "URLs nettoyées (pas de tracking)",
            Status.PASS, Severity.MAJOR,
            evidence=f"{len(p.urls)} URL(s) sans tracking",
        )
    samples = "; ".join(f"{truncate(u, 60)} → {truncate(c, 60)}" for u, c, _ in dirty[:3])
    return RuleResult(
        "F26", "F", "URLs nettoyées (pas de tracking)",
        Status.FAIL, Severity.MAJOR,
        evidence=f"{len(dirty)} URL(s) avec params (utm_/token/session): {samples}",
        recommendation="Supprimer les paramètres de tracking avant intégration.",
        remediable=True,
    )


@register
def rule_url_visible(p: ParsedDoc, _: Settings) -> RuleResult:
    if not p.hyperlinks:
        if p.file_type == "pdf":
            return RuleResult(
                "F27", "F", "URL affichée en clair (pas masquée)",
                Status.NOT_VERIFIABLE, Severity.MAJOR,
                evidence="Hyperliens PDF non analysés",
            )
        return RuleResult(
            "F27", "F", "URL affichée en clair (pas masquée)",
            Status.PASS, Severity.MAJOR, evidence="Aucun hyperlien",
        )
    masked = [
        (d, t)
        for d, t in p.hyperlinks
        if d and t and d.strip() != t.strip() and not d.startswith("http")
    ]
    if not masked:
        return RuleResult(
            "F27", "F", "URL affichée en clair (pas masquée)",
            Status.PASS, Severity.MAJOR,
            evidence=f"{len(p.hyperlinks)} hyperliens, URL visible",
        )
    samples = "; ".join(f"'{truncate(d, 30)}' → {truncate(t, 60)}" for d, t in masked[:3])
    return RuleResult(
        "F27", "F", "URL affichée en clair (pas masquée)",
        Status.FAIL, Severity.MAJOR,
        evidence=f"{len(masked)} lien(s) masqué(s): {samples}",
        recommendation="Afficher l'URL complète plutôt qu'un texte d'ancre.",
    )
