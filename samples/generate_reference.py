"""Generate a reference DOCX that passes every blocking rule.

Usage:
    python3 samples/generate_reference.py

Produces ``samples/20260506_Guidelines_KMDoc_Reference.docx``.

Each design choice below is annotated with the rule ID from the
official KM typology that it satisfies.
"""
from __future__ import annotations

import os

from docx import Document


REF_FILENAME = "20260506_Guidelines_KMDoc_Reference.docx"


def _add_field(doc: Document, label: str, value: str) -> None:
    doc.add_paragraph(f"{label} : {value}")


def build_reference() -> Document:
    doc = Document()

    # A1 : nom de fichier au format AAAAMMJJ_Sujet_Type_Extra.ext
    # H29 : étiquette de confidentialité Public ou Interne
    doc.add_heading("Métadonnées du document", level=1)
    _add_field(doc, "Auteur", "Jane Doe (équipe Knowledge Management)")
    _add_field(doc, "Sensibilité", "Public")

    # Section "Objectif" — utile pour la lisibilité humaine, même si A3
    # a été retiré du périmètre de l'audit automatique (géré désormais
    # par l'interface Domino).
    doc.add_heading("Objectif du document", level=1)
    doc.add_paragraph(
        "Ce document présente les bonnes pratiques applicables à la rédaction "
        "de notes documentaires destinées à un traitement automatique."
    )

    # B5 : titres descriptifs, hiérarchie multi-niveaux (H1 + H2)
    # B6 : titres et sous-titres suffisants (densité)
    doc.add_heading("Public cible", level=2)
    doc.add_paragraph(
        "Le public cible regroupe les contributeurs internes et les "
        "relecteurs qualité de la base documentaire."
    )

    doc.add_heading("Périmètre fonctionnel", level=2)
    doc.add_paragraph(
        "Le périmètre couvre la rédaction, la structuration et la "
        "publication de notes documentaires courtes."
    )

    doc.add_heading("Bonnes pratiques de structuration", level=1)
    doc.add_paragraph(
        "Les pratiques décrites favorisent la lisibilité humaine et "
        "l'intelligibilité par des outils automatiques."
    )

    doc.add_heading("Hiérarchie des titres", level=2)
    doc.add_paragraph(
        "Chaque section utilise un titre descriptif et hiérarchisé avec "
        "des niveaux cohérents tout au long du document."
    )

    doc.add_heading("Concision des phrases", level=2)
    doc.add_paragraph(
        "Les phrases restent courtes et claires pour faciliter la lecture "
        "et la reformulation par les outils KM."
    )

    # C7 : première occurrence de chaque acronyme accompagnée de l'expansion
    doc.add_heading("Glossaire des acronymes", level=1)
    doc.add_paragraph(
        "Les acronymes utilisés dans ce document sont définis ci-dessous "
        "pour assurer leur compréhension."
    )
    doc.add_paragraph("KM (Knowledge Management) : gestion de la connaissance organisationnelle.")
    doc.add_paragraph("IA (Intelligence Artificielle) : ensemble de modèles automatiques de traitement.")

    doc.add_heading("Synthèse et recommandations", level=1)
    doc.add_paragraph(
        "Une rédaction structurée et lisible reste la meilleure garantie "
        "d'une bonne intégration dans les outils KM et IA."
    )

    return doc


def main() -> str:
    doc = build_reference()
    out_dir = os.path.dirname(os.path.abspath(__file__))
    out_path = os.path.join(out_dir, REF_FILENAME)
    doc.save(out_path)
    print(f"Generated: {out_path}")
    return out_path


if __name__ == "__main__":
    main()
