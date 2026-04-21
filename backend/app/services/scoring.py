"""Scoring model. Transparent and deterministic.

Formula:
  1. Base: 100.
  2. Subtract weighted penalty per finding:
       critical: 10, serious: 5, moderate: 2, minor: 1
  3. Apply a page-importance multiplier: homepage (priority >= 90) counts 1.5x.
  4. Apply a repeat-rule penalty: a rule that appears on > 50% of pages is
     treated as systemic and gets a 1.25x multiplier (caps at 2x if it appears
     on every page).
  5. Clamp to [0, 100]. Grade bands:
       90-100 → A, 80-89 → B, 70-79 → C, 60-69 → D, <60 → F
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Dict, Iterable, List, Tuple


_SEVERITY_WEIGHTS = {"critical": 10, "serious": 5, "moderate": 2, "minor": 1}


def compute_score(
    findings: List[Dict[str, Any]], pages: List[Dict[str, Any]]
) -> Tuple[float, str, Dict[str, Any]]:
    if not pages:
        return 100.0, "A", {
            "findings_total": 0,
            "severity_breakdown": {},
            "top_rules": [],
        }

    pages_by_id = {p["id"]: p for p in pages if p.get("id")}
    total_pages = max(1, len(pages_by_id))

    # Rule → number of distinct pages it appears on.
    rule_page_counts: Dict[str, set] = {}
    for f in findings:
        rule_page_counts.setdefault(f.get("rule_id", "unknown"), set()).add(
            f.get("page_id")
        )
    systemic: Dict[str, float] = {}
    for rule, pages_seen in rule_page_counts.items():
        ratio = len(pages_seen) / total_pages
        if ratio > 0.5:
            systemic[rule] = 1.25 + min(0.75, ratio - 0.5)
        else:
            systemic[rule] = 1.0

    severity_counts: Counter = Counter()
    rule_counts: Counter = Counter()
    penalty = 0.0
    for f in findings:
        sev = f.get("severity", "minor")
        rule = f.get("rule_id", "unknown")
        severity_counts[sev] += 1
        rule_counts[rule] += 1

        base = _SEVERITY_WEIGHTS.get(sev, 1)
        page = pages_by_id.get(f.get("page_id"), {})
        page_mult = 1.5 if (page.get("priority") or 0) >= 90 else 1.0
        rule_mult = systemic.get(rule, 1.0)
        penalty += base * page_mult * rule_mult

    score = max(0.0, min(100.0, 100.0 - penalty))
    grade = (
        "A" if score >= 90 else
        "B" if score >= 80 else
        "C" if score >= 70 else
        "D" if score >= 60 else
        "F"
    )

    stats = {
        "findings_total": len(findings),
        "severity_breakdown": dict(severity_counts),
        "top_rules": rule_counts.most_common(10),
        "systemic_rules": [r for r, m in systemic.items() if m > 1.0],
        "pages_scanned": total_pages,
        "pages_with_findings": len(
            {f.get("page_id") for f in findings if f.get("page_id")}
        ),
        "with_screenshot_pct": _with_pct(findings, "annotated_screenshot_path"),
        "with_wcag_evidence_pct": _with_pct(findings, "wcag_refs"),
    }
    return round(score, 2), grade, stats


def _with_pct(findings: Iterable[Dict[str, Any]], key: str) -> float:
    findings = list(findings)
    if not findings:
        return 0.0
    n = 0
    for f in findings:
        v = f.get(key)
        if v:
            if isinstance(v, list):
                if len(v) > 0:
                    n += 1
            else:
                n += 1
    return round(100.0 * n / len(findings), 1)
