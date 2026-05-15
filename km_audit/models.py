"""Domain models: parse output, rule outcomes, audit result."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class Status(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    WARN = "WARN"
    NOT_VERIFIABLE = "NOT_VERIFIABLE"


class Severity(str, Enum):
    BLOCKER = "BLOCKER"
    MAJOR = "MAJOR"
    MINOR = "MINOR"


@dataclass
class RuleResult:
    rule_id: str
    category: str
    title: str
    status: Status
    severity: Severity
    evidence: str = ""
    location: str = ""
    recommendation: str = ""
    remediable: bool = False  # whether the remediation engine can act on it

    def is_blocker_fail(self) -> bool:
        return self.severity is Severity.BLOCKER and self.status is Status.FAIL


@dataclass
class ParsedDoc:
    file_name: str
    file_type: str
    raw_bytes: bytes

    text_blocks: List[str] = field(default_factory=list)
    # Localisation lisible par humain pour chaque ``text_blocks`` (même
    # taille). Exemples : "Slide 3", "Page 2", "Section: Glossaire",
    # "Feuille: Données". Sert à enrichir ``RuleResult.location``.
    text_block_locations: List[str] = field(default_factory=list)
    headings: List[Tuple[int, str]] = field(default_factory=list)
    tables: List[Dict[str, Any]] = field(default_factory=list)
    images: List[Dict[str, Any]] = field(default_factory=list)
    urls: List[str] = field(default_factory=list)
    hyperlinks: List[Tuple[str, str]] = field(default_factory=list)  # (display, target)
    pages: int = 0
    extra: Dict[str, Any] = field(default_factory=dict)
    parse_warning: Optional[str] = None

    def locate(self, block_index: int) -> str:
        """Return a human-readable location for the n-th text block."""
        if 0 <= block_index < len(self.text_block_locations):
            return self.text_block_locations[block_index]
        return ""


@dataclass
class DocumentAuditResult:
    file_name: str
    file_type: str
    file_size: int
    audit_date: str
    rules: List[RuleResult] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    score: float = 0.0
    verdict: str = "Feu Rouge"
    parse_error: Optional[str] = None

    @property
    def blocking_failures(self) -> List[RuleResult]:
        return [r for r in self.rules if r.is_blocker_fail()]

    @property
    def failures(self) -> List[RuleResult]:
        return [r for r in self.rules if r.status is Status.FAIL]

    @property
    def warnings(self) -> List[RuleResult]:
        return [r for r in self.rules if r.status is Status.WARN]
