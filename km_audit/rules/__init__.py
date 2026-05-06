"""Rule registry and runner.

Each category module declares its rules via the ``@register`` decorator.
``run_all`` iterates the registry and produces a list of RuleResult.
"""
from __future__ import annotations

from typing import Callable, List

from ..config import Settings
from ..models import ParsedDoc, RuleResult, Severity, Status

RuleFn = Callable[[ParsedDoc, Settings], RuleResult]
_REGISTRY: List[RuleFn] = []


def register(fn: RuleFn) -> RuleFn:
    """Decorator to add a rule callable to the registry."""
    _REGISTRY.append(fn)
    return fn


def all_rules() -> List[RuleFn]:
    return list(_REGISTRY)


def run_all(parsed: ParsedDoc, settings: Settings) -> List[RuleResult]:
    results: List[RuleResult] = []
    for fn in _REGISTRY:
        try:
            results.append(fn(parsed, settings))
        except Exception as exc:  # pragma: no cover - defensive
            results.append(
                RuleResult(
                    rule_id="ERR",
                    category="?",
                    title=f"Erreur d'évaluation ({getattr(fn, '__name__', 'rule')})",
                    status=Status.NOT_VERIFIABLE,
                    severity=Severity.MINOR,
                    evidence=str(exc),
                )
            )
    return results


# Eagerly import all rule modules so the registry is populated.
# Order matters: rules are evaluated in registration order, so we keep the
# official typology order A → B → C → D → E → F → G → H → I.
from . import (  # noqa: E402, F401
    identification,    # A
    structure,         # B
    text_formatting,   # C
    images,            # D
    tables,            # E
    diagrams,          # F
    urls,              # G
    sensitive as sensitive_rules,  # H
    practices,         # I
)
