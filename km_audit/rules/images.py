"""Category C – Images (legends, quality)."""
from __future__ import annotations

from ..config import Settings
from ..models import ParsedDoc, RuleResult, Severity, Status
from . import register
from ._helpers import full_text


@register
def rule_image_legends(p: ParsedDoc, _: Settings) -> RuleResult:
    if not p.images:
        return RuleResult(
            "C10", "C", "Légende sous chaque image informative",
            Status.PASS, Severity.MAJOR, evidence="Aucune image détectée",
        )
    text = full_text(p).lower()
    hint = sum(text.count(h) for h in ("figure", "schéma", "schema", "illustration", "capture"))
    if hint >= len(p.images):
        return RuleResult(
            "C10", "C", "Légende sous chaque image informative",
            Status.PASS, Severity.BLOCKER,
            evidence=f"{hint} mentions de légendes / {len(p.images)} images",
        )
    if hint > 0:
        return RuleResult(
            "C10", "C", "Légende sous chaque image informative",
            Status.WARN, Severity.BLOCKER,
            evidence=f"{hint} mentions de légendes / {len(p.images)} images",
            recommendation="Ajouter une légende explicite (Figure X – ...) sous chaque image informative.",
        )
    return RuleResult(
        "C10", "C", "Légende sous chaque image informative",
        Status.FAIL, Severity.BLOCKER,
        evidence=f"{len(p.images)} images sans mention 'Figure/Schéma/...'",
        recommendation="Ajouter une légende (Figure X – ...) sous chaque image informative.",
    )


@register
def rule_image_quality(p: ParsedDoc, settings: Settings) -> RuleResult:
    if not p.images:
        return RuleResult(
            "C11", "C", "Qualité des images (résolution, netteté)",
            Status.PASS, Severity.MAJOR, evidence="Aucune image",
        )
    bad = []
    for img in p.images:
        w = img.get("width", 0) or 0
        h = img.get("height", 0) or 0
        blur = img.get("blur", -1)
        # python-docx widths come in EMU (914400/inch); rough heuristic to convert
        if w and w > 100000:
            w_px = int(w / 9525)
            h_px = int(h / 9525)
        else:
            w_px, h_px = w, h
        too_small = w_px and h_px and (
            w_px < settings.min_image_width or h_px < settings.min_image_height
        )
        too_blurry = 0 < blur < settings.blur_variance_threshold
        if too_small or too_blurry:
            bad.append(f"{w_px}x{h_px}px blur={blur:.1f}")
    if not bad:
        return RuleResult(
            "C11", "C", "Qualité des images (résolution, netteté)",
            Status.PASS, Severity.MAJOR, evidence=f"{len(p.images)} images OK",
        )
    return RuleResult(
        "C11", "C", "Qualité des images (résolution, netteté)",
        Status.WARN, Severity.MAJOR,
        evidence=f"{len(bad)} image(s) sous seuil: " + "; ".join(bad[:5]),
        recommendation="Remplacer par des images haute résolution / non floues.",
    )
