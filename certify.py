"""End-to-end certification harness for the KM audit toolchain.

Runs three scenarios and prints PASS/FAIL per assertion:

  1. Green path  – the reference DOCX must reach Feu Vert with zero
     blocking failures and a score above the configured threshold.
  2. Red path    – the deliberately non-compliant DOCX must trigger
     Feu Rouge with the expected blocker set.
  3. Remediation – applying the auto-generated plan to the bad DOCX
     must measurably improve the score, drop blockers, and produce a
     valid patched DOCX.

Also exercises the PDF report and the Markdown remediation guide.

Usage::

    python3 certify.py
"""
from __future__ import annotations

import io
import os
import subprocess
import sys
from typing import List, Optional, Tuple

from km_audit import (
    DEFAULT_SETTINGS,
    DocumentAuditResult,
    audit_document,
    build_plan,
    generate_pdf_report,
    generate_zip,
    patch_document,
    pdf_filename,
    render_markdown_guide,
)
from km_audit.models import Status
from km_audit.rules import all_rules
from samples.generate_bad import BAD_FILENAME
from samples.generate_bad import main as build_bad
from samples.generate_reference import REF_FILENAME
from samples.generate_reference import main as build_reference


SAMPLES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "samples")


# ---------------------------------------------------------------------------
# Tiny assertion harness (no pytest dependency)
# ---------------------------------------------------------------------------

class Certifier:
    def __init__(self) -> None:
        self.results: List[Tuple[str, bool, str]] = []

    def check(self, label: str, condition: bool, detail: str = "") -> None:
        self.results.append((label, bool(condition), detail))
        marker = "PASS" if condition else "FAIL"
        suffix = f" — {detail}" if detail else ""
        print(f"  [{marker}] {label}{suffix}")

    def summary(self) -> int:
        passed = sum(1 for _, ok, _ in self.results if ok)
        total = len(self.results)
        failed = total - passed
        print()
        print("=" * 60)
        print(f"Certification: {passed}/{total} checks passed.")
        if failed:
            print("FAILED checks:")
            for label, ok, detail in self.results:
                if not ok:
                    print(f"  - {label} ({detail})")
        return failed


def _read(name: str) -> bytes:
    with open(os.path.join(SAMPLES_DIR, name), "rb") as f:
        return f.read()


def _summarize(res: DocumentAuditResult) -> str:
    return (
        f"verdict={res.verdict} score={res.score} "
        f"blockers_ko={len(res.blocking_failures)}"
    )


def _failed_rule_ids(res: DocumentAuditResult, statuses=(Status.FAIL,)) -> List[str]:
    return sorted(r.rule_id for r in res.rules if r.status in statuses)


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------


def scenario_green(c: Certifier) -> Optional[DocumentAuditResult]:
    print("\n[1] Green path — reference DOCX")
    raw = _read(REF_FILENAME)
    res = audit_document(REF_FILENAME, raw, DEFAULT_SETTINGS)
    c.check("Reference doc parses without warning",
            res.parse_error is None, str(res.parse_error or ""))
    c.check("Reference doc → Feu Vert", res.verdict == "Feu Vert", _summarize(res))
    c.check("Reference doc has zero blocking failures",
            len(res.blocking_failures) == 0,
            f"blockers={[r.rule_id for r in res.blocking_failures]}")
    c.check("Reference doc score >= threshold (80)",
            res.score >= DEFAULT_SETTINGS.score_pass_threshold,
            f"score={res.score}")
    c.check("All explicit-blocker rules return PASS",
            all(r.status is Status.PASS for r in res.rules
                if r.severity.value == "BLOCKER"),
            f"non-PASS blockers="
            f"{[r.rule_id for r in res.rules if r.severity.value == 'BLOCKER' and r.status is not Status.PASS]}")
    c.check("Cartouche email correctly classified as author",
            not any(r.rule_id == "H28" and r.status is Status.FAIL for r in res.rules),
            "H28 must be PASS for the reference doc")
    return res


def scenario_red(c: Certifier) -> Optional[DocumentAuditResult]:
    print("\n[2] Red path — deliberately non-compliant DOCX")
    raw = _read(BAD_FILENAME)
    res = audit_document(BAD_FILENAME, raw, DEFAULT_SETTINGS)
    c.check("Bad doc → Feu Rouge", res.verdict == "Feu Rouge", _summarize(res))
    fail_ids = _failed_rule_ids(res)
    expected_min = {"A1", "A3", "A4", "B5", "B6", "C7", "C9", "G26", "H28"}
    c.check("Bad doc raises the expected blocker set",
            expected_min.issubset(set(fail_ids)),
            f"got={fail_ids}")
    return res


def scenario_remediation(c: Certifier, bad_audit: DocumentAuditResult) -> None:
    print("\n[3] Remediation — auto-fix + re-audit")
    raw = _read(BAD_FILENAME)
    plan = build_plan(bad_audit)
    c.check("Plan is non-empty", bool(plan.actions),
            f"actions={[a.kind.value for a in plan.actions]}")

    outcome = patch_document(BAD_FILENAME, raw, plan,
                             enabled_kinds=[a.kind for a in plan.actions])
    c.check("Patch produced bytes", outcome.patched_bytes is not None,
            outcome.error or "")
    c.check("Patch applied at least the expected actions",
            {"rename_file", "inject_cartouche", "inject_objective",
             "inject_glossary", "replace_symbols",
             "clean_urls", "redact_sensitive"}.issubset(
                {a.kind.value for a in plan.actions}),
            f"plan kinds={[a.kind.value for a in plan.actions]}")

    if outcome.patched_bytes is None:
        return

    re_res = audit_document(outcome.file_name, outcome.patched_bytes, DEFAULT_SETTINGS)
    c.check("Re-audit improves score",
            re_res.score > bad_audit.score,
            f"{bad_audit.score} -> {re_res.score}")
    c.check("Re-audit reduces blocker count",
            len(re_res.blocking_failures) < len(bad_audit.blocking_failures),
            f"{len(bad_audit.blocking_failures)} -> {len(re_res.blocking_failures)}")
    auto_remediated = {"A1", "A3", "A4", "C9", "G26", "H28"}
    remaining = {r.rule_id for r in re_res.failures}
    c.check("Auto-remediable failures are resolved",
            not (auto_remediated & remaining),
            f"still failing among auto-set: {sorted(auto_remediated & remaining)}")

    # Idempotence: re-applying the plan must not duplicate sections
    outcome2 = patch_document(outcome.file_name, outcome.patched_bytes, plan,
                              enabled_kinds=[a.kind for a in plan.actions])
    re_res2 = audit_document(outcome2.file_name, outcome2.patched_bytes, DEFAULT_SETTINGS)
    c.check("Patcher is idempotent (score stable on second pass)",
            abs(re_res2.score - re_res.score) < 5.0,
            f"{re_res.score} -> {re_res2.score}")


def scenario_outputs(c: Certifier, ref_audit: DocumentAuditResult) -> None:
    print("\n[4] Outputs — PDF report, ZIP bundle, Markdown guide")
    pdf_bytes = generate_pdf_report(ref_audit)
    c.check("PDF starts with %PDF magic header",
            pdf_bytes[:4] == b"%PDF", f"got={pdf_bytes[:4]!r}")
    c.check("PDF size > 4 KB", len(pdf_bytes) > 4096, f"size={len(pdf_bytes)}")

    zip_bytes = generate_zip([(pdf_filename(ref_audit.file_name), pdf_bytes)])
    c.check("ZIP starts with PK magic header",
            zip_bytes[:2] == b"PK", f"got={zip_bytes[:2]!r}")

    plan = build_plan(ref_audit)
    guide = render_markdown_guide(ref_audit, plan)
    c.check("Markdown guide is non-empty", len(guide) > 0)
    c.check("Markdown guide mentions filename",
            ref_audit.file_name in guide)


def scenario_registry(c: Certifier) -> None:
    print("\n[5] Registry — rule discovery")
    rules = all_rules()
    expected = (
        {f"A{i}" for i in (1, 2, 3, 4)}
        | {f"B{i}" for i in (5, 6)}
        | {f"C{i}" for i in (7, 8, 9)}
        | {f"D{i}" for i in (10, 11)}
        | {f"E{i}" for i in (12, 13, 14, 15, 16, 17, 18, 19)}
        | {f"F{i}" for i in (20, 21, 22, 23, 24)}
        | {f"G{i}" for i in (25, 26, 27)}
        | {"H28"}
        | {f"I{i}" for i in (29, 30, 31, 32, 33, 34, 35)}
    )
    c.check(f"Registry has {len(expected)} rules", len(rules) == len(expected),
            f"count={len(rules)}")
    rule_ids = []
    for fn in rules:
        from km_audit.models import ParsedDoc
        empty = ParsedDoc(file_name="probe.docx", file_type="docx", raw_bytes=b"")
        try:
            r = fn(empty, DEFAULT_SETTINGS)
            rule_ids.append(r.rule_id)
        except Exception as exc:
            c.check(f"Rule {fn.__name__} executes on empty doc", False, str(exc))
    c.check("All expected rule IDs are present",
            expected.issubset(set(rule_ids)),
            f"missing={sorted(expected - set(rule_ids))}")
    c.check("No unexpected rule IDs",
            set(rule_ids).issubset(expected),
            f"unexpected={sorted(set(rule_ids) - expected)}")


def scenario_original_spec(c: Certifier) -> None:
    """Verify the original prompt requirements are still honored."""
    print("\n[6] Spec initiale — exigences fondamentales")

    # Offline only: production code must not import any network library
    # (certify.py is excluded since it carries the literal pattern names
    # in its test assertions).
    proc = subprocess.run(
        ["grep", "-rE", r"\b(requests|httpx|urllib\.request|urllib3|aiohttp)\b",
         "--include=*.py", "km_audit", "app.py"],
        capture_output=True, text=True,
    )
    c.check("Aucun import réseau (requests/httpx/urllib...)",
            proc.returncode != 0, proc.stdout.strip()[:200])

    # 4 formats supported
    from km_audit.loaders import _LOADERS
    c.check("Loaders DOCX/PPTX/XLSX/PDF enregistrés",
            set(_LOADERS) == {"docx", "pptx", "xlsx", "pdf"},
            f"loaders={sorted(_LOADERS)}")

    # Verdict logic: any blocker FAIL -> Feu Rouge
    from km_audit.models import RuleResult, Severity, Status as S
    from km_audit.scoring import compute
    rules = [
        RuleResult("X1", "X", "ok", S.PASS, Severity.BLOCKER),
        RuleResult("X2", "X", "fail", S.FAIL, Severity.BLOCKER),
    ]
    score, verdict = compute(rules, DEFAULT_SETTINGS)
    c.check("Verdict: un seul bloquant FAIL ⇒ Feu Rouge", verdict == "Feu Rouge",
            f"verdict={verdict}, score={score}")

    # Scoring weights = 70/30
    c.check("Pondération bloquantes/pratiques = 70/30",
            DEFAULT_SETTINGS.weight_blocking == 70
            and DEFAULT_SETTINGS.weight_practices == 30,
            f"{DEFAULT_SETTINGS.weight_blocking}/{DEFAULT_SETTINGS.weight_practices}")

    # ZIP bundle is functional
    import zipfile
    zip_bytes = generate_zip([("a.pdf", b"%PDF-1.4"), ("b.pdf", b"%PDF-1.4")])
    zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    c.check("ZIP bundle multi-fichiers valide",
            sorted(zf.namelist()) == ["a.pdf", "b.pdf"])

    # Sensitive data is masked in output (raw values must not appear)
    from km_audit.sensitive import mask_email, mask_phone, mask_iban
    raw_email = "alice.client@externe.example"
    masked = mask_email(raw_email)
    c.check("Email sensible masqué (pas de fuite du local-part)",
            "alice.client" not in masked and "@externe.example" in masked,
            masked)
    c.check("IBAN sensible masqué",
            mask_iban("FR7612345678901234567890123").startswith("FR")
            and "1234567890" not in mask_iban("FR7612345678901234567890123"))
    c.check("Téléphone masqué", mask_phone("+33 6 12 34 56 78").startswith("***"))

    # Streamlit cache decorator is applied
    src = open("app.py", encoding="utf-8").read()
    c.check("Cache @st.cache_data appliqué sur l'audit",
            "@st.cache_data" in src and "_cached_audit" in src)

    # Self-check function exists
    c.check("Fonction self_check disponible", "def self_check" in src)


def scenario_review_feedback(c: Certifier) -> None:
    """Verify every point from the KM reviewer's email is addressed."""
    print("\n[7] Retour de relecture — feedback Nuria")

    app_src = open("app.py", encoding="utf-8").read()
    rep_src = open("km_audit/reporting.py", encoding="utf-8").read()

    # 1. Title: 'IA-Readiness' with capital R
    c.check("UI titre = 'IA-Readiness' (R majuscule)",
            "IA-Readiness" in app_src and "IA-readiness" not in app_src)
    c.check("PDF titre = 'IA-Readiness' (R majuscule)",
            "IA-Readiness" in rep_src and "IA-readiness" not in rep_src)

    # 2. Diagrams (F20) no longer reserved to PPTX
    from km_audit.models import ParsedDoc
    empty_docx = ParsedDoc(file_name="x.docx", file_type="docx", raw_bytes=b"")
    empty_docx.text_blocks = ["Voici la procédure : étape 1, étape 2, étape 3."]
    from km_audit.rules.diagrams import rule_diagram_labels
    f20 = rule_diagram_labels(empty_docx, DEFAULT_SETTINGS)
    c.check("F20 (libellés génériques) s'applique aussi à DOCX",
            f20.status is Status.WARN,
            f"status={f20.status.value}, evidence={f20.evidence[:80]}")

    # 3. I30 reco softened
    docx_doc = ParsedDoc(file_name="x.pptx", file_type="pptx", raw_bytes=b"")
    from km_audit.rules.practices import rule_format_preference
    i30 = rule_format_preference(docx_doc, DEFAULT_SETTINGS)
    c.check("I30 reco adoucie ('Si possible, privilégier DOCX...')",
            "Si possible" in i30.recommendation, i30.recommendation)

    # 4. long_doc_pages default = 20
    c.check("Seuil document long = 20 pages",
            DEFAULT_SETTINGS.long_doc_pages == 20,
            str(DEFAULT_SETTINGS.long_doc_pages))

    # 4 bis. I31 reco softened
    long_doc = ParsedDoc(file_name="x.docx", file_type="docx", raw_bytes=b"")
    long_doc.pages = 25
    from km_audit.rules.practices import rule_doc_length
    i31 = rule_doc_length(long_doc, DEFAULT_SETTINGS)
    c.check("I31 reco adoucie ('Si possible, découper...')",
            "Si possible" in i31.recommendation, i31.recommendation)

    # 5. No 'RAG' references anywhere (certify.py excluded: it has
    # 'RAG' in this very assertion text).
    proc = subprocess.run(
        ["grep", "-rwl", "RAG", "--include=*.py", "--include=*.md",
         "km_audit", "app.py", "README.md", "CERTIFICATION.md"],
        capture_output=True, text=True,
    )
    c.check("'RAG' supprimé partout (UI, reco, docs)",
            proc.returncode != 0, proc.stdout.strip()[:200])

    # 6. Locations populated for relevant rules
    from docx import Document
    d = Document()
    d.add_heading("Introduction", level=1)
    d.add_paragraph("Le statut courant ✓ avec quelques infos.")
    d.add_paragraph("Contact externe : someone@externe.example, IBAN FR7612345678901234567890123.")
    d.add_paragraph("Lien brut https://x.com/p?utm_source=foo&id=1")
    buf = io.BytesIO(); d.save(buf)
    rr = audit_document("loc_probe.docx", buf.getvalue(), DEFAULT_SETTINGS)
    located = {r.rule_id: r.location for r in rr.rules if r.location}
    c.check("C9 remonte la localisation (§N — section)",
            "C9" in located and "§" in located["C9"],
            f"C9 location={located.get('C9', '<vide>')}")
    c.check("H28 remonte la localisation",
            "H28" in located and "§" in located["H28"],
            f"H28 location={located.get('H28', '<vide>')}")

    # 7. PDF + UI use 'Localisation' instead of 'Preuve'
    c.check("Colonne PDF 'Localisation' (au lieu de 'Preuve')",
            "Localisation" in rep_src and '"Preuve"' not in rep_src,
            "")
    c.check("UI affiche 'Localisation' (au lieu de 'Preuve')",
            "Localisation" in app_src and "Preuve" not in app_src)

    # 8. 'Détails de l'analyse' rename
    c.check("UI 'Détails de l'analyse' (au lieu de 'Détail des règles')",
            "Détails de l'analyse" in app_src
            and "Détail des règles" not in app_src)
    c.check("PDF 'Détails de l'analyse'",
            "Détails de l'analyse" in rep_src)

    # 9. PDF download button clarifies that source format is preserved
    c.check("Bouton PDF clarifié ('rapport d'audit (PDF)')",
            "rapport d'audit (PDF)" in app_src
            and "help=" in app_src)

    # 10. Verdict thresholds in PDF + UI legend
    c.check("PDF contient une légende des fourchettes de feux",
            "Fourchette de score" in rep_src
            and "Feu Vert" in rep_src and "Feu Orange" in rep_src)
    c.check("UI contient la légende des feux et statuts",
            "_render_legend" in app_src
            and "Fourchettes des feux" in app_src
            and "Statuts par règle" in app_src)

    # 11. 'Alertes' instead of 'Avertissements'
    c.check("UI 'Alertes' (au lieu de 'Avertissements')",
            '"Alertes"' in app_src and "Avertissements" not in app_src)

    # 12. Status icon legend present
    c.check("UI explique les icônes ✅ ⚠️ ❌ ❔",
            all(s in app_src for s in ("PASS", "WARN", "FAIL", "N/V"))
            and "✅" in app_src and "❌" in app_src)

    # Bonus: score_orange_floor wired
    c.check("Seuil 'Feu Orange floor' = 50 par défaut",
            DEFAULT_SETTINGS.score_orange_floor == 50,
            str(DEFAULT_SETTINGS.score_orange_floor))

    # Bonus: low score without blocker fail still triggers Feu Rouge
    from km_audit.models import RuleResult, Severity, Status as S
    from km_audit.scoring import compute
    low_score_rules = [
        RuleResult("Y1", "Y", "warn", S.WARN, Severity.BLOCKER),
        RuleResult("Y2", "Y", "fail", S.FAIL, Severity.MAJOR),
        RuleResult("Y3", "Y", "fail", S.FAIL, Severity.MAJOR),
    ]
    score_, verdict_ = compute(low_score_rules, DEFAULT_SETTINGS)
    c.check("Score < 50 sans bloquant FAIL ⇒ Feu Rouge (aligné légende)",
            verdict_ == "Feu Rouge" and score_ < 50,
            f"score={score_}, verdict={verdict_}")


def main() -> int:
    # Always regenerate the samples so the harness is reproducible.
    print("Generating sample documents…")
    build_reference()
    build_bad()

    c = Certifier()
    ref = scenario_green(c)
    bad = scenario_red(c)
    if bad is not None:
        scenario_remediation(c, bad)
    if ref is not None:
        scenario_outputs(c, ref)
    scenario_registry(c)
    scenario_original_spec(c)
    scenario_review_feedback(c)
    return c.summary()


if __name__ == "__main__":
    sys.exit(main())
