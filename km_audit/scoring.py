"""Score and verdict computation."""
from __future__ import annotations

from typing import List, Tuple

from .config import Settings
from .models import RuleResult, Severity, Status

_STATUS_WEIGHTS = {
    Status.PASS: 1.0,
    Status.WARN: 0.5,
    Status.NOT_VERIFIABLE: 0.7,
    Status.FAIL: 0.0,
}


def _ratio(items: List[RuleResult]) -> float:
    if not items:
        return 1.0
    return sum(_STATUS_WEIGHTS.get(r.status, 0.0) for r in items) / len(items)


def compute(rules: List[RuleResult], settings: Settings) -> Tuple[float, str]:
    blocking = [r for r in rules if r.severity is Severity.BLOCKER]
    practices = [r for r in rules if r.severity is not Severity.BLOCKER]

    score = (
        _ratio(blocking) * settings.weight_blocking
        + _ratio(practices) * settings.weight_practices
    )

    if any(r.is_blocker_fail() for r in rules) or score < settings.score_orange_floor:
        verdict = "Feu Rouge"
    elif score >= settings.score_pass_threshold:
        verdict = "Feu Vert"
    else:
        verdict = "Feu Orange"

    return round(score, 1), verdict
