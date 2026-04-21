"""Persistence step.

Writes all accumulated findings (with bboxes, WCAG refs, remediations) to the
DB and updates the scan row with its score + summary. This is a LangGraph
node rather than being interleaved because it's more reliable to persist
after all analysis has completed — a crash mid-analysis leaves the scan in
a clean 'partial' state instead of with half-filled findings.
"""
from __future__ import annotations

from typing import Any, Dict

from ..core.logging import get_logger
from ..db.base import session_scope
from ..db.repository import create_finding, update_scan
from .state import RawFinding, ScanState

_log = get_logger(__name__)


async def persist_results(state: ScanState) -> ScanState:
    scan_id = state["scan_id"]
    findings = state.get("findings") or []

    async with session_scope() as session:
        for f in findings:
            try:
                await create_finding(
                    session,
                    scan_id=scan_id,
                    page_id=f["page_id"],
                    rule_id=f.get("rule_id") or "unknown",
                    title=f.get("title") or "Accessibility issue",
                    description=f.get("description"),
                    help_text=f.get("help_text"),
                    help_url=f.get("help_url"),
                    severity=f.get("severity", "minor"),
                    source=f.get("source", "axe"),
                    confidence=f.get("confidence", "medium"),
                    selector=f.get("selector"),
                    html_snippet=(f.get("html_snippet") or "")[:4000],
                    bbox_json=f.get("bbox"),
                    annotated_screenshot_path=f.get("annotated_screenshot_path"),
                    wcag_refs_json=f.get("wcag_refs") or [],
                    remediation_json=f.get("remediation"),
                )
            except Exception as e:
                _log.warning("finding persist skipped: %s", e)

        status = "succeeded" if not state.get("errors") else "partial"
        await update_scan(
            session,
            scan_id,
            status=status,
            score=state.get("score"),
            grade=state.get("grade"),
            stats_json=state.get("stats"),
            executive_summary=state.get("executive_summary"),
            summary_md=_build_summary_md(state),
        )
    _log.info("persisted %d findings for scan %s (status=%s)", len(findings), scan_id, status)
    return state


def _build_summary_md(state: ScanState) -> str:
    stats: Dict[str, Any] = state.get("stats") or {}
    lines = [
        f"# Accessibility scan — {state.get('domain','')}",
        "",
        f"**Score:** {state.get('score')} / 100 (**{state.get('grade')}**)",
        "",
        state.get("executive_summary") or "",
        "",
        "## Severity breakdown",
    ]
    for sev in ("critical", "serious", "moderate", "minor"):
        lines.append(f"- **{sev}**: {stats.get('severity_breakdown', {}).get(sev, 0)}")
    lines += [
        "",
        "## Top priorities",
        *[f"- {p}" for p in (stats.get("top_priorities") or [])],
        "",
        f"_{stats.get('business_value','')}_",
    ]
    return "\n".join(lines)
