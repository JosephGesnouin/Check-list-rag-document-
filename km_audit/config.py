"""Settings, regex constants, and category metadata."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field, fields
from typing import Dict


CATEGORIES: Dict[str, str] = {
    "A": "Permettre l'identification du document",
    "B": "Mise en forme du document et sa structure",
    "C": "Mise en forme du texte",
    "D": "Gestion des images",
    "E": "Gestion des tableaux",
    "F": "Gestion des diagrammes / schémas",
    "G": "Gestion des URLs",
    "H": "Données sensibles",
    "I": "Bonnes pratiques générales",
}


@dataclass(frozen=True)
class Settings:
    """User-tunable thresholds. Frozen so it can be hashed for caching."""

    max_paragraph_chars: int = 600
    max_avg_sentence_words: int = 25
    min_image_width: int = 500
    min_image_height: int = 350
    blur_variance_threshold: float = 80.0
    long_doc_pages: int = 20
    min_headings_per_pages: float = 0.5
    score_pass_threshold: int = 80
    score_orange_floor: int = 50
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

# Mots tout-en-majuscules qui ne sont PAS des acronymes ; filtrés en C7
# pour éviter les faux positifs (cf. retour métier sur ACCOUNT, ANNEX,
# BUSINESS, etc.). Liste extensible.
ACRONYM_STOPLIST = frozenset({
    # English common words often capitalised in titles/headers
    "ABOUT", "ACCESS", "ACCOUNT", "ACCOUNTS", "ACT", "ACTION", "ACTIONS",
    "ADD", "ADDED", "ADDRESS", "ADMIN", "ADVISER", "AGENT", "AGREE",
    "AGREEMENT", "AI", "ALL", "ALSO", "AMOUNT", "AND", "ANNEX", "ANNEXES",
    "ANY", "APP", "APPLICATION", "APPLY", "APPROVAL", "AREA", "AS",
    "ASSET", "ASSETS", "AT", "ATTACHMENT", "AUDIT", "AUTHORISED",
    "AVERAGE", "BANK", "BASE", "BASED", "BE", "BEFORE", "BENEFITS",
    "BETWEEN", "BOTH", "BRANCH", "BREAK", "BUDGET", "BUSINESS", "BUT",
    "BY", "CALENDAR", "CALL", "CAN", "CAP", "CAPACITY", "CAPITAL", "CARD",
    "CARE", "CASE", "CASH", "CC", "CENTRAL", "CHANGE", "CHECK", "CIRCLE",
    "CITY", "CLIENT", "CLIENTS", "CLOSE", "CODE", "COMMENT", "COMMON",
    "COMPANY", "COMPLETE", "COMPUTER", "CONFIRM", "CONTACT", "CONTENT",
    "CONTEXT", "CONTRACT", "CONTROL", "COPY", "COPYRIGHT", "CORE", "COST",
    "COUNTRY", "COVER", "COVERED", "CREDIT", "CRITICAL", "CURRENCY",
    "CURRENT", "CUSTOMER", "DATA", "DATE", "DAY", "DEBT", "DECEMBER",
    "DEFAULT", "DELIVERY", "DEPARTMENT", "DEPOSIT", "DETAILS", "DOCUMENT",
    "DURING", "EACH", "EARLY", "EFFECTIVE", "EMAIL", "END", "ENTERPRISE",
    "ENTITY", "EQUITY", "ETC", "EUR", "EURO", "EXAMPLE", "EXCLUDED",
    "EXIT", "EXTRA", "FALSE", "FAQ", "FEE", "FEES", "FILE", "FINANCE",
    "FINANCIAL", "FIRM", "FIRST", "FIX", "FIXED", "FLOAT", "FLOW", "FOR",
    "FORM", "FRAME", "FRANCE", "FROM", "FULL", "FULLY", "FUND",
    "FURTHER", "GENERAL", "GLOBAL", "GO", "GOOD", "GROUP", "HALF", "HAS",
    "HAVE", "HEAD", "HERE", "HIGH", "HISTORY", "HOME", "HOUR", "HOW", "I",
    "ID", "IDEA", "IF", "IMPACT", "IMPORTANT", "IN", "INC", "INDEX",
    "INFO", "INPUT", "INSIDE", "INSTANCE", "INSURANCE", "INTERNAL",
    "INTERNATIONAL", "INTO", "INVOICE", "IS", "ISSUE", "IT", "ITEM",
    "ITS", "JANUARY", "JUNE", "JULY", "KEY", "LARGE", "LAST", "LATE",
    "LAW", "LEAD", "LEAVE", "LEGAL", "LENGTH", "LETTER", "LEVEL",
    "LIABILITY", "LIMIT", "LINE", "LINK", "LIST", "LOAN", "LOCAL",
    "LOG", "LONG", "LOW", "LTD", "MADE", "MAIN", "MAJOR", "MAKE", "MANY",
    "MARCH", "MARGIN", "MARKET", "MATCH", "MAX", "MAY", "MEAN", "MID",
    "MIN", "MINOR", "MISC", "MIX", "MIXED", "MODEL", "MONTH", "MORE",
    "MOST", "MOVE", "MUST", "NAME", "NEED", "NEW", "NEXT", "NO", "NONE",
    "NOT", "NOTE", "NOTES", "NOTHING", "NOW", "NUMBER", "OBJECT", "OF",
    "OFF", "OFFER", "OFFICE", "OK", "OLD", "ON", "ONCE", "ONE", "ONLY",
    "OPEN", "OPTION", "OR", "ORDER", "OTHER", "OUT", "OVER", "OWN",
    "PAID", "PARENT", "PART", "PASS", "PAYMENT", "PER", "PERCENT",
    "PERIOD", "PERSON", "PHONE", "PIECE", "PLAN", "PLEASE", "POLICY",
    "POSITION", "POST", "POWER", "PREVIOUS", "PRICE", "PRINT", "PRIORITY",
    "PROCESS", "PRODUCT", "PROFILE", "PROJECT", "PROOF", "PUBLIC",
    "QUARTER", "QUICK", "RATE", "READ", "READY", "REAL", "RECORD", "REF",
    "REFERENCE", "REGION", "REPORT", "REQUEST", "RESULT", "REVENUE",
    "REVIEW", "RIGHT", "RISK", "ROLE", "ROUND", "RULE", "SAFE", "SALE",
    "SALES", "SAME", "SAMPLE", "SAVE", "SCALE", "SCHEMA", "SCOPE",
    "SEARCH", "SECTION", "SECTOR", "SEE", "SELF", "SEND", "SERVER",
    "SERVICE", "SET", "SETUP", "SHARE", "SHEET", "SHOP", "SHORT", "SIDE",
    "SIGN", "SIMPLE", "SINCE", "SINGLE", "SIZE", "SO", "SOLD", "SOLE",
    "SOLUTION", "SOME", "SOON", "SOURCE", "SPACE", "SPECIAL", "SPLIT",
    "STAFF", "STAGE", "STAND", "START", "STATE", "STATUS", "STEP", "STOP",
    "STOCK", "SUB", "SUBJECT", "SUM", "SUMMARY", "SUPPORT", "SYSTEM",
    "TABLE", "TARGET", "TASK", "TAX", "TEAM", "TERM", "TEXT", "THAN",
    "THAT", "THE", "THEM", "THEN", "THESE", "THEY", "THIS", "THOSE",
    "TIME", "TIPS", "TITLE", "TO", "TODO", "TOOL", "TOP", "TOTAL",
    "TRADE", "TRAIN", "TRAINING", "TRUE", "TYPE", "UNDER", "UNIT",
    "UPDATE", "UPON", "USA", "USE", "USED", "USER", "VALUE", "VAT",
    "VAULT", "VERY", "VIEW", "VISIT", "VOLUME", "WAY", "WE", "WEB",
    "WEEK", "WHAT", "WHEN", "WHERE", "WHICH", "WHILE", "WHO", "WHY",
    "WILL", "WITH", "WORK", "WORKING", "WORLD", "YEAR", "YES", "YOU",
    "YOUR", "ZONE",
    # Frequent French months/words capitalised in headers
    "AVRIL", "AOUT", "AOÛT", "BIEN", "DECEMBRE", "DÉCEMBRE", "DEPUIS",
    "DOCUMENT", "ENFIN", "ENTRE", "FEVRIER", "FÉVRIER", "FRANCE", "ICI",
    "JANVIER", "JUILLET", "MAI", "MARDI", "MARS", "MONTANT", "NIVEAU",
    "NOTE", "NOTES", "NOVEMBRE", "OCTOBRE", "OUI", "PAGE", "PAYS",
    "POUR", "REMARQUE", "SAUF", "SEPTEMBRE", "SI", "SUR", "TYPE", "UN",
    "UNE", "VOIR",
})

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
# Détection brute des séquences chiffrées (au moins 8 chiffres, séparateurs
# autorisés). La règle H28 ajoute par-dessus un filtre mot-clé (« Tél »,
# « Téléphone », ...) pour ne pas confondre avec des dates, des références
# de fichiers ou des paramètres d'URL.
PHONE_RE = re.compile(r"(?<!\d)\+?\d[\d\s\.\-\(\)/]{6,28}\d(?!\d)")
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
