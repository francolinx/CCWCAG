"""Synthesis / Reporting Agent.

Aggregates findings across pages, computes a score and grade, and produces an
executive summary. Uses the LLM if configured, else a deterministic template.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List

from ..core.logging import get_logger
from ..db.base import session_scope
from ..db.repository import get_pages
from ..services.llm import get_llm
from ..services.scoring import compute_score
from .prompts import SYNTHESIS_SYSTEM
from .state import RawFinding, ScanState

_log = get_logger(__name__)


def _templated_summary(
    score: float, grade: str, stats: Dict[str, Any], domain: str
) -> Dict[str, Any]:
    sev = stats.get("severity_breakdown", {})
    top_rules = [r for r, _ in (stats.get("top_rules") or [])]
    priorities = top_rules[:3] or ["Review findings for prioritisation"]

    exec_summary = (
        f"{domain} scanned with a score of {score}/100 (grade {grade}). "
        f"{stats.get('findings_total', 0)} accessibility issues were detected "
        f"across {stats.get('pages_scanned', 0)} pages. "
        f"Severity: "
        f"{sev.get('critical', 0)} critical, "
        f"{sev.get('serious', 0)} serious, "
        f"{sev.get('moderate', 0)} moderate, "
        f"{sev.get('minor', 0)} minor. "
        f"{int(stats.get('with_wcag_evidence_pct', 0))}% of findings are grounded in WCAG evidence."
    )
    return {
        "executive_summary": exec_summary,
        "top_priorities": priorities,
        "business_value": (
            "Fixing these issues broadens your customer reach, reduces legal "
            "exposure under ADA / EAA, and typically improves SEO and "
            "conversion rates."
        ),
    }


async def synthesize(state: ScanState) -> ScanState:
    scan_id = state["scan_id"]

    async with session_scope() as session:
        page_rows = await get_pages(session, scan_id)
        pages = [{"id": p.id, "priority": p.priority, "url": p.url} for p in page_rows]

    findings: List[RawFinding] = state.get("findings") or []
    score, grade, stats = compute_score(findings, pages)

    llm = get_llm()
    summary_obj: Dict[str, Any]
    if llm.enabled:
        payload = {
            "domain": state.get("domain"),
            "score": score,
            "grade": grade,
            "stats": stats,
            "top_findings": [
                {
                    "rule_id": f.get("rule_id"),
                    "title": f.get("title"),
                    "severity": f.get("severity"),
                    "page_url": f.get("page_url"),
                }
                for f in findings[:30]
            ],
        }
        obj = llm.json_complete(
            system=SYNTHESIS_SYSTEM,
            user=json.dumps(payload),
            temperature=0.3,
            max_tokens=500,
        )
        summary_obj = obj or _templated_summary(score, grade, stats, state.get("domain", ""))
    else:
        summary_obj = _templated_summary(score, grade, stats, state.get("domain", ""))

    state["score"] = score
    state["grade"] = grade
    state["stats"] = stats
    state["executive_summary"] = summary_obj.get("executive_summary")
    state.setdefault("stats", {}).update(
        {
            "top_priorities": summary_obj.get("top_priorities", []),
            "business_value": summary_obj.get("business_value"),
        }
    )
    _log.info("synthesis complete: score=%s grade=%s", score, grade)
    return state
