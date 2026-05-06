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


def detect_sensitive(text: str, head_chars: int = 2000) -> Dict[str, List[str]]:
    """Return a dict of category -> list of (raw) matches.

    Heuristique « auteur » : un email présent dans la zone cartouche
    (premiers ``head_chars`` caractères) est considéré comme l'email de
    l'auteur uniquement si le label « Auteur » apparaît dans cette même
    zone. Cela évite de blanchir les emails externes lorsque le document
    n'a pas de cartouche identifiable.
    """
    head = text[:head_chars]
    author_emails = set()
    if re.search(r"\bauteur\b", head, re.IGNORECASE):
        for em in EMAIL_RE.findall(head):
            author_emails.add(em)

    emails = [e for e in EMAIL_RE.findall(text) if e not in author_emails]
    phones = [p for p in PHONE_RE.findall(text) if len(re.sub(r"\D", "", p)) >= 8]
    ibans = IBAN_RE.findall(text)
    addresses = POSTAL_ADDR_RE.findall(text)
    client_ids = CLIENT_ID_RE.findall(text)

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
