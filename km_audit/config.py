"""Settings, regex constants, and category metadata."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field, fields
from typing import Dict


CATEGORIES: Dict[str, str] = {
    "A": "Identification",
    "B": "Structure",
    "C": "Images",
    "D": "Tableaux",
    "E": "Diagrammes",
    "F": "URLs",
    "G": "Bonnes pratiques",
    "H": "Données sensibles",
}


@dataclass(frozen=True)
class Settings:
    """User-tunable thresholds. Frozen so it can be hashed for caching."""

    max_paragraph_chars: int = 600
    max_avg_sentence_words: int = 25
    min_image_width: int = 500
    min_image_height: int = 350
    blur_variance_threshold: float = 80.0
    long_doc_pages: int = 10
    min_headings_per_pages: float = 0.5
    score_pass_threshold: int = 80
    weight_blocking: int = 70
    weight_practices: int = 30

    def to_dict(self) -> Dict[str, float]:
        return asdict(self)

    def cache_key(self) -> tuple:
        return tuple(sorted(self.to_dict().items()))


DEFAULT_SETTINGS = Settings()


# ---------------------------------------------------------------------------
# Regex / token constants
# ---------------------------------------------------------------------------
NAMING_REGEX = re.compile(
    r"^(?P<date>\d{8})_(?P<subject>[^_]+)_(?P<doctype>[^_]+)(?:_(?P<extra>.+))?\."
    r"(?P<ext>docx|pptx|pdf|xlsx)$",
    re.IGNORECASE,
)

REQUIRED_CARTOUCHE_FIELDS = (
    "Auteur",
    "Email",
    "Equipe",
    "Thème",
    "Type de document",
    "Description",
    "Mot",  # mot(s) clé(s)
    "Périmètre",
    "Entité",
    "Date d'échéance",
)

OBJECTIVE_HINTS = ("objectif", "objective", "description", "but ", "purpose")
GLOSSARY_HINTS = ("glossaire", "glossary", "acronymes", "acronyms", "définitions")

EMOJI_OR_SYMBOL_RE = re.compile(
    "[" "←-⇿" "☀-➿" "\U0001F300-\U0001FAFF" "]"
)
URL_RE = re.compile(r"https?://[^\s\)\]\>]+", re.IGNORECASE)
ACRONYM_RE = re.compile(r"\b([A-Z]{2,10})s?\b")

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE_RE = re.compile(
    r"(?:(?<!\d)(?:\+\d{1,3}[\s.\-]?)?(?:\(?\d{2,4}\)?[\s.\-]?){2,5}\d{2,4}(?!\d))"
)
IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]){11,30}\b")
POSTAL_ADDR_RE = re.compile(
    r"\b\d{1,4}\s+(?:rue|avenue|av\.|bd|boulevard|place|chemin|impasse|allée|route|"
    r"street|st\.|road|rd\.)\b",
    re.IGNORECASE,
)
CLIENT_ID_RE = re.compile(
    r"\b(?:client|customer|account|compte)[\s#:_-]*\d{4,}\b",
    re.IGNORECASE,
)

TRACKING_PARAMS = (
    "utm_",
    "gclid",
    "fbclid",
    "session",
    "sessionid",
    "token",
    "auth",
    "tracking",
)

SYMBOL_REPLACEMENTS = {
    "✓": "oui",
    "✔": "oui",
    "✗": "non",
    "✘": "non",
    "❌": "non",
    "❎": "non",
    "✅": "oui",
    "➜": "->",
    "⇒": "=>",
    "→": "->",
    "←": "<-",
    "⬅": "<-",
    "⮕": "->",
    "▶": "-",
    "●": "-",
    "■": "-",
    "◆": "-",
}


def settings_from_dict(d: Dict) -> Settings:
    """Build a Settings from a partial dict, ignoring unknown keys."""
    known = {f.name for f in fields(Settings)}
    return Settings(**{k: v for k, v in d.items() if k in known})
