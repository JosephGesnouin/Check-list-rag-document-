"""Streamlit UI for the KM Document Audit toolchain.

Thin presentation layer. All business logic lives in the ``km_audit``
package. Three tabs:

  * Audit: upload + per-document verdict, score, breakdown.
  * Remédiation: action plan, selective auto-fix (DOCX) and Markdown guide.
  * Règles / Checklist: human-readable description of the rule set.
"""
from __future__ import annotations

import datetime as _dt
import sys
from dataclasses import fields
from typing import List, Tuple

import streamlit as st

from km_audit import (
    CATEGORIES,
    DEFAULT_SETTINGS,
    DocumentAuditResult,
    Settings,
    audit_document,
    build_plan,
    generate_pdf_report,
    generate_zip,
    patch_document,
    pdf_filename,
    render_markdown_guide,
)
from km_audit.config import settings_from_dict
from km_audit.models import Status
from km_audit.remediation import ActionKind
from km_audit.rules import all_rules


# ---------------------------------------------------------------------------
# Cached audit (key is filename + bytes hash + settings tuple)
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def _cached_audit(file_name: str, raw: bytes, settings_key: tuple) -> DocumentAuditResult:
    settings = settings_from_dict(dict(settings_key))
    return audit_document(file_name, raw, settings)


# ---------------------------------------------------------------------------
# Sidebar – settings
# ---------------------------------------------------------------------------

def _settings_panel() -> Settings:
    st.sidebar.header("Paramètres")
    s = DEFAULT_SETTINGS.to_dict()
    s["max_paragraph_chars"] = st.sidebar.number_input(
        "Longueur max paragraphe (chars)", 100, 5000, s["max_paragraph_chars"], 50
    )
    s["max_avg_sentence_words"] = st.sidebar.number_input(
        "Longueur moyenne max phrase (mots)", 5, 60, s["max_avg_sentence_words"], 1
    )
    s["min_image_width"] = st.sidebar.number_input(
        "Largeur min image (px)", 100, 5000, s["min_image_width"], 50
    )
    s["min_image_height"] = st.sidebar.number_input(
        "Hauteur min image (px)", 100, 5000, s["min_image_height"], 50
    )
    s["blur_variance_threshold"] = st.sidebar.number_input(
        "Seuil flou (variance Laplacien)", 0.0, 5000.0,
        float(s["blur_variance_threshold"]), 5.0,
    )
    s["long_doc_pages"] = st.sidebar.number_input(
        "Document long si > N pages", 1, 200, s["long_doc_pages"], 1
    )
    s["min_headings_per_pages"] = st.sidebar.slider(
        "Densité min titres / page", 0.0, 5.0,
        float(s["min_headings_per_pages"]), 0.1,
    )
    s["score_pass_threshold"] = st.sidebar.slider(
        "Seuil de conformité (Feu Vert)", 0, 100, s["score_pass_threshold"]
    )
    s["weight_blocking"] = st.sidebar.slider(
        "Poids des règles bloquantes", 0, 100, s["weight_blocking"]
    )
    s["weight_practices"] = 100 - s["weight_blocking"]
    st.sidebar.caption(f"Poids bonnes pratiques: {s['weight_practices']}")
    return settings_from_dict(s)


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------

_STATUS_ICON = {
    Status.PASS: "✅",
    Status.FAIL: "❌",
    Status.WARN: "⚠️",
    Status.NOT_VERIFIABLE: "❔",
}
_VERDICT_BADGE = {"Feu Vert": "🟢", "Feu Orange": "🟠", "Feu Rouge": "🔴"}


def _truncate(s: str, n: int = 220) -> str:
    s = (s or "").replace("\n", " ").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def _render_summary(res: DocumentAuditResult) -> None:
    badge = _VERDICT_BADGE.get(res.verdict, "⚪")
    cols = st.columns([3, 1, 1, 1])
    cols[0].markdown(f"### {badge} **{res.file_name}**  \n_{res.verdict}_")
    cols[1].metric("Score", f"{res.score}/100")
    cols[2].metric("Bloquants KO", len(res.blocking_failures))
    cols[3].metric("Avertissements", len(res.warnings))
    if res.parse_error:
        st.warning(res.parse_error)
    if res.blocking_failures:
        with st.container(border=True):
            st.error("Points bloquants")
            for r in res.blocking_failures:
                st.markdown(f"- **{r.rule_id} {r.title}** — {_truncate(r.evidence)}")


def _render_rules_detail(res: DocumentAuditResult) -> None:
    with st.expander("Détail des règles", expanded=False):
        for cat_code, cat_label in CATEGORIES.items():
            cat_rules = [r for r in res.rules if r.category == cat_code]
            if not cat_rules:
                continue
            st.markdown(f"**{cat_code} – {cat_label}**")
            for r in cat_rules:
                icon = _STATUS_ICON.get(r.status, "•")
                st.markdown(
                    f"{icon} `{r.rule_id}` **{r.title}**  "
                    f"_(sévérité: {r.severity.value})_  \n"
                    f"&nbsp;&nbsp;Preuve: {_truncate(r.evidence) or '—'}  \n"
                    f"&nbsp;&nbsp;Reco: {_truncate(r.recommendation) or '—'}"
                )


def _render_remediation(
    res: DocumentAuditResult,
    raw: bytes,
    settings_key: tuple,
) -> None:
    plan = build_plan(res)
    if not plan.actions:
        st.success("Aucune action corrective requise pour ce document.")
        return

    st.markdown("**Plan de remédiation détecté.** Cocher les actions à appliquer.")
    selected: List[ActionKind] = []
    for action in plan.actions:
        applicable = action.supports_patch(res.file_type)
        label = (
            f"**{action.title}** — _{action.description}_  \n"
            f"Règle: `{action.rule_id}` · Auto sur ce format: "
            f"{'✅ oui' if applicable else '⚠️ non (manuel)'}"
        )
        key = f"action::{res.file_name}::{action.kind.value}"
        if st.checkbox(label, value=applicable, key=key):
            selected.append(action.kind)

    btn_cols = st.columns([1, 1, 2])

    if btn_cols[0].button(
        "🛠 Appliquer & re-auditer",
        key=f"apply::{res.file_name}",
        use_container_width=True,
    ):
        outcome = patch_document(res.file_name, raw, plan, enabled_kinds=selected)
        if outcome.error:
            st.error(outcome.error)
        if outcome.applied:
            st.success("Actions appliquées : " + " ; ".join(outcome.applied))
        if outcome.skipped:
            st.info("Actions ignorées : " + " ; ".join(outcome.skipped))
        if outcome.patched_bytes is not None:
            st.download_button(
                "⬇️ Télécharger le document corrigé",
                data=outcome.patched_bytes,
                file_name=outcome.file_name,
                mime=_mime_for(res.file_type),
                key=f"dl_patched::{res.file_name}",
            )
            # Re-audit on the patched bytes
            new_res = _cached_audit(outcome.file_name, outcome.patched_bytes, settings_key)
            st.markdown("#### Résultat après correction")
            _render_summary(new_res)

    if btn_cols[1].button(
        "📝 Générer guide Markdown",
        key=f"md::{res.file_name}",
        use_container_width=True,
    ):
        guide = render_markdown_guide(res, plan)
        st.download_button(
            "⬇️ Télécharger le guide (.md)",
            data=guide.encode("utf-8"),
            file_name=f"{res.file_name}__remediation.md",
            mime="text/markdown",
            key=f"dl_md::{res.file_name}",
        )
        with st.expander("Aperçu du guide", expanded=False):
            st.markdown(guide)


def _mime_for(file_type: str) -> str:
    return {
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "pdf": "application/pdf",
    }.get(file_type, "application/octet-stream")


def _render_rules_doc():
    st.subheader("Règles appliquées")
    st.write(f"**{len(all_rules())}** règles enregistrées dans la registry.")
    for cat_code, cat_label in CATEGORIES.items():
        st.markdown(f"### {cat_code} – {cat_label}")
        st.write(_RULES_DOC.get(cat_code, "—"))


_RULES_DOC = {
    "A": "A1 nommage, A2 cartouche, A3 objectif, A4 acronymes 1re occurrence, A5 glossaire (BLOQUANT).",
    "B": "B6 hiérarchie de titres, B7 densité de titres, B8 textboxes inutiles (PPTX), B9 symboles dans phrases.",
    "C": "C10 légendes d'images, C11 résolution + variance Laplacien (flou).",
    "D": "D12 fusions, D13 bordures (XLSX), D14 en-têtes en gras, D15 titres/légendes, D16 symboles, "
         "D17 pagination (NV), D18 tableau natif vs image.",
    "E": "E19 lisibilité diagrammes (heuristique PPTX: nb shapes, libellés génériques).",
    "F": "F25 contexte autour des URLs, F26 nettoyage (utm/token/session), F27 URL en clair.",
    "G": "G28 coupures, G29 DOCX préféré, G30 longueur, G31 en-têtes/pieds, G32 phrases courtes, "
         "G33 alignement, G34 longueur paragraphes.",
    "H": "H34 détection emails / téléphones / IBAN / adresses / identifiants client (masqués dans le rapport).",
}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    st.set_page_config(page_title="KM Document Audit", page_icon="📋", layout="wide")
    st.title("📋 KM Document Audit – Quality Gate IA-readiness")
    st.caption("Audit local et offline – aucun appel réseau.")

    settings = _settings_panel()
    settings_key = settings.cache_key()

    tab_audit, tab_remediation, tab_rules = st.tabs(
        ["Audit", "Remédiation", "Règles / Checklist"]
    )

    with tab_rules:
        _render_rules_doc()

    with tab_audit:
        files = st.file_uploader(
            "Glisser-déposer un ou plusieurs documents (DOCX, PPTX, PDF, XLSX)",
            type=["docx", "pptx", "pdf", "xlsx"],
            accept_multiple_files=True,
            key="uploader_audit",
        )
        if not files:
            st.info("Aucun fichier chargé pour l'instant.")
        else:
            reports: List[Tuple[str, bytes]] = []
            for f in files:
                raw = f.getvalue()
                try:
                    res = _cached_audit(f.name, raw, settings_key)
                except Exception as exc:  # pragma: no cover
                    st.error(f"Erreur d'audit ({f.name}): {exc}")
                    continue
                with st.container(border=True):
                    _render_summary(res)
                    _render_rules_detail(res)
                    pdf_bytes = generate_pdf_report(res)
                    reports.append((pdf_filename(res.file_name), pdf_bytes))
                    st.download_button(
                        f"📄 Générer PDF – {res.file_name}",
                        data=pdf_bytes,
                        file_name=pdf_filename(res.file_name),
                        mime="application/pdf",
                        key=f"pdf::{res.file_name}",
                    )
            if len(reports) > 1:
                st.markdown("---")
                zip_bytes = generate_zip(reports)
                st.download_button(
                    "🗂 Tout télécharger (ZIP)",
                    data=zip_bytes,
                    file_name=f"KM_AUDIT_{_dt.date.today().strftime('%Y%m%d')}.zip",
                    mime="application/zip",
                )

    with tab_remediation:
        st.markdown(
            "Cet onglet propose un **plan de remédiation** par document : actions concrètes,"
            " application automatique sur DOCX (cartouche, glossaire, symboles, URLs, masquage),"
            " ou export d'un guide Markdown pour les autres formats."
        )
        rfiles = st.file_uploader(
            "Documents à remédier",
            type=["docx", "pptx", "pdf", "xlsx"],
            accept_multiple_files=True,
            key="uploader_remediation",
        )
        if not rfiles:
            st.info("Charger un document pour générer un plan de remédiation.")
            return
        for f in rfiles:
            raw = f.getvalue()
            try:
                res = _cached_audit(f.name, raw, settings_key)
            except Exception as exc:  # pragma: no cover
                st.error(f"Erreur d'audit ({f.name}): {exc}")
                continue
            with st.container(border=True):
                _render_summary(res)
                _render_remediation(res, raw, settings_key)


# ---------------------------------------------------------------------------
# Self-check
# ---------------------------------------------------------------------------

def self_check() -> int:
    from km_audit.config import NAMING_REGEX
    from km_audit.rules.urls import clean_url
    from km_audit.sensitive import mask_email, mask_iban

    failures = 0

    def _check(label: str, cond: bool) -> None:
        nonlocal failures
        print(("OK  " if cond else "FAIL") + " " + label)
        if not cond:
            failures += 1

    _check("naming valid", bool(NAMING_REGEX.match("20260121_Guidelines_KM_Cash.pptx")))
    _check("naming invalid", not NAMING_REGEX.match("guidelines.pptx"))

    cleaned, drop = clean_url("https://x.com/a?utm_source=foo&id=42&token=abc")
    _check("url cleaning drops tracking", "utm_source=foo" in drop and "token=abc" in drop)
    _check("url cleaning keeps id", "id=42" in cleaned)

    _check("email mask", mask_email("john.doe@example.com").endswith("@example.com"))
    _check("iban mask shorter", len(mask_iban("FR7612345678901234567890123")) < 27)

    _check("settings has expected fields",
           {"weight_blocking", "weight_practices"} <= {f.name for f in fields(Settings)})

    print(f"\n{failures} failure(s)")
    return failures


if __name__ == "__main__":
    if "--self-check" in sys.argv[1:]:
        sys.exit(self_check())
    main()
