"""Sensitive-data masking and detection helpers."""
from __future__ import annotations

import re
from typing import Dict, List

from .config import (
    CLIENT_ID_RE,
    EMAIL_RE,
    IBAN_RE,
    PHONE_RE,
    POSTAL_ADDR_RE,
    URL_RE,
)


_PHONE_CONTEXT_RE = re.compile(
    r"(?i)\b(?:t[ée]l(?:[ée]phone)?|phone|mobile|portable|fixe|gsm|ligne|fax)"
    r"[\s\.:\-]+$"
)


def mask_email(e: str) -> str:
    try:
        local, domain = e.split("@", 1)
        return (local[0] + "***" if local else "***") + "@" + domain
    except Exception:
        return "***@***"


def mask_phone(p: str) -> str:
    digits = re.sub(r"\D", "", p)
    if len(digits) < 4:
        return "***"
    return "***" + digits[-2:]


def mask_iban(s: str) -> str:
    s = s.replace(" ", "")
    if len(s) < 6:
        return "***"
    return s[:2] + "***" + s[-4:]


def mask_address(_: str) -> str:
    return "[adresse retirée]"


def _strip_urls(text: str) -> str:
    """Remove URLs from ``text`` so digit sequences inside them are not
    misinterpreted as phone numbers or other sensitive patterns."""
    return URL_RE.sub(" [URL] ", text)


def _detect_phones(text: str) -> List[str]:
    """Phone detection requires an explicit phone keyword right before the
    number (within ~30 chars), to avoid false positives on dates, file
    references or any long digit sequence."""
    phones: List[str] = []
    for m in PHONE_RE.finditer(text):
        # Skip if fewer than 8 digits overall (eliminates years, page refs).
        if len(re.sub(r"\D", "", m.group(0))) < 8:
            continue
        context = text[max(0, m.start() - 30): m.start()]
        if _PHONE_CONTEXT_RE.search(context):
            phones.append(m.group(0))
    return phones


def detect_sensitive(text: str, head_chars: int = 2000) -> Dict[str, List[str]]:
    """Return a dict of category -> list of (raw) matches.

    Heuristiques renforcées suite au retour métier :

    * URLs : retirées du texte avant détection, leurs paramètres
      numériques ne sont plus pris pour des numéros de téléphone.
    * Téléphones : exige un mot-clé (`tél`, `téléphone`, `phone`,
      `mobile`...) dans les 30 caractères précédents.
    * Auteur : un email présent dans la zone cartouche est considéré
      comme l'email de l'auteur si le label « Auteur » apparaît dans
      cette même zone.
    """
    safe_text = _strip_urls(text)
    head = safe_text[:head_chars]
    author_emails = set()
    if re.search(r"\bauteur\b", head, re.IGNORECASE):
        for em in EMAIL_RE.findall(head):
            author_emails.add(em)

    emails = [e for e in EMAIL_RE.findall(safe_text) if e not in author_emails]
    phones = _detect_phones(safe_text)
    ibans = IBAN_RE.findall(safe_text)
    addresses = POSTAL_ADDR_RE.findall(safe_text)
    client_ids = CLIENT_ID_RE.findall(safe_text)

    return {
        "emails": emails,
        "phones": phones,
        "ibans": ibans,
        "addresses": addresses,
        "client_ids": client_ids,
    }


def has_findings(findings: Dict[str, List[str]]) -> bool:
    return any(v for v in findings.values())


def summarize(findings: Dict[str, List[str]]) -> List[str]:
    out = []
    if findings.get("emails"):
        out.append(f"emails: {', '.join(mask_email(e) for e in findings['emails'][:5])}")
    if findings.get("phones"):
        out.append(f"téléphones: {', '.join(mask_phone(p) for p in findings['phones'][:5])}")
    if findings.get("ibans"):
        out.append(f"IBAN: {', '.join(mask_iban(i) for i in findings['ibans'][:3])}")
    if findings.get("addresses"):
        out.append(f"adresses: {len(findings['addresses'])} occurrence(s)")
    if findings.get("client_ids"):
        out.append(f"identifiants client: {len(findings['client_ids'])} occurrence(s)")
    return out
