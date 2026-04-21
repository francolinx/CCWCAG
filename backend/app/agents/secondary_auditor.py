"""Secondary Audit Agent.

Runs a deterministic HTML-level auditor over each captured page and merges
the results with the axe findings. Cross-validation is used to set
confidence tags:

  * axe + secondary both flag the rule  → confidence "high"
  * axe-only                             → confidence "high" (axe is our primary)
  * secondary-only                       → confidence "medium"
"""
from __future__ import annotations

from typing import Dict, List, Set, Tuple

from ..core.logging import get_logger
from ..services.secondary_audit import audit_html
from .state import RawFinding, ScanState

_log = get_logger(__name__)


def _key(f: RawFinding) -> Tuple[str, str]:
    return (f.get("rule_id") or "", (f.get("selector") or "").strip())


async def secondary_audit(state: ScanState) -> ScanState:
    opts = state.get("options") or {}
    if not bool(opts.get("use_secondary", True)):
        return state

    findings: List[RawFinding] = list(state.get("findings") or [])
    captures = state.get("captures") or []

    # Build an index of (rule_id, selector) for axe findings per page.
    axe_by_page: Dict[str, Set[Tuple[str, str]]] = {}
    axe_rules_by_page: Dict[str, Set[str]] = {}
    for f in findings:
        axe_by_page.setdefault(f["page_id"], set()).add(_key(f))
        axe_rules_by_page.setdefault(f["page_id"], set()).add(f.get("rule_id") or "")

    for cap in captures:
        page_id = cap.get("page_id") or ""
        html = cap.get("html")
        if not html or not page_id:
            continue
        issues = audit_html(html)
        for iss in issues:
            key = (iss.rule_id, (iss.selector or "").strip())
            axe_rules = axe_rules_by_page.get(page_id, set())
            confidence = "high" if iss.rule_id in axe_rules else "medium"

            if key in axe_by_page.get(page_id, set()):
                # Same (rule, selector) already caught by axe — just promote confidence.
                for f in findings:
                    if f["page_id"] == page_id and _key(f) == key:
                        f["confidence"] = "high"
                        break
                continue

            findings.append(
                RawFinding(
                    rule_id=iss.rule_id,
                    title=iss.title,
                    description=iss.description,
                    help_text=iss.help_text,
                    help_url=None,
                    severity=iss.severity,
                    source="secondary",
                    selector=iss.selector,
                    html_snippet=iss.html_snippet,
                    page_id=page_id,
                    page_url=cap.get("final_url") or cap.get("url") or "",
                    confidence=confidence,
                    wcag_refs=[],
                    remediation=None,
                    bbox=None,
                    annotated_screenshot_path=None,
                )
            )

    state["findings"] = findings
    _log.info("after secondary audit: %d total findings", len(findings))
    return state
