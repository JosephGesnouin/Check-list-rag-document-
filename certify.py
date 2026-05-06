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
            not any(r.rule_id == "H34" and r.status is Status.FAIL for r in res.rules),
            "H34 must be PASS for the reference doc")
    return res


def scenario_red(c: Certifier) -> Optional[DocumentAuditResult]:
    print("\n[2] Red path — deliberately non-compliant DOCX")
    raw = _read(BAD_FILENAME)
    res = audit_document(BAD_FILENAME, raw, DEFAULT_SETTINGS)
    c.check("Bad doc → Feu Rouge", res.verdict == "Feu Rouge", _summarize(res))
    fail_ids = _failed_rule_ids(res)
    expected_min = {"A1", "A3", "A5", "B9", "F26", "H34"}
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
    auto_remediated = {"A1", "A3", "A5", "B9", "F26", "H34"}
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
    c.check("Registry has 30 rules", len(rules) == 30, f"count={len(rules)}")
    rule_ids = []
    for fn in rules:
        # Probe each rule against an empty ParsedDoc to read the rule_id.
        from km_audit.models import ParsedDoc
        empty = ParsedDoc(file_name="probe.docx", file_type="docx", raw_bytes=b"")
        try:
            r = fn(empty, DEFAULT_SETTINGS)
            rule_ids.append(r.rule_id)
        except Exception as exc:
            c.check(f"Rule {fn.__name__} executes on empty doc", False, str(exc))
    expected = {f"A{i}" for i in (1, 2, 3, 4, 5)} | \
        {f"B{i}" for i in (6, 7, 8, 9)} | \
        {"C10", "C11"} | \
        {f"D{i}" for i in (12, 13, 14, 15, 16, 17, 18)} | \
        {"E19"} | \
        {f"F{i}" for i in (25, 26, 27)} | \
        {f"G{i}" for i in (28, 29, 30, 31, 32, 33, 34)} | \
        {"H34"}
    c.check("All expected rule IDs are present",
            expected.issubset(set(rule_ids)),
            f"missing={sorted(expected - set(rule_ids))}")


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
    return c.summary()


if __name__ == "__main__":
    sys.exit(main())
