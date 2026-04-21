"""Memory / History Agent.

Compares the just-completed scan to the most recent previous scan for the
same domain (if any) and persists a comparison row. The API's
`/scans/{id}/compare/{prev_id}` endpoint can also recompute on demand.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from ..core.logging import get_logger
from ..db.base import session_scope
from ..db.repository import (
    get_findings,
    list_scans_for_domain,
    save_comparison,
)
from ..models.orm import Finding, Scan
from .state import ScanState

_log = get_logger(__name__)


def _fingerprint(f: Finding) -> Tuple[str, str]:
    # Rule + selector is the most stable identifier across scans.
    return (f.rule_id, (f.selector or "").strip())


def _diff_summaries(current: List[Finding], previous: List[Finding]) -> Dict[str, Any]:
    cur = {_fingerprint(f): f for f in current}
    prev = {_fingerprint(f): f for f in previous}
    cur_keys = set(cur.keys())
    prev_keys = set(prev.keys())

    def _info(f: Finding) -> Dict[str, Any]:
        return {
            "rule_id": f.rule_id,
            "title": f.title,
            "severity": f.severity,
            "selector": f.selector,
            "page_id": f.page_id,
        }

    new = [_info(cur[k]) for k in cur_keys - prev_keys]
    resolved = [_info(prev[k]) for k in prev_keys - cur_keys]
    recurring = [_info(cur[k]) for k in cur_keys & prev_keys]
    return {
        "new_issues": new,
        "resolved_issues": resolved,
        "recurring_issues": recurring,
        "delta": {
            "new": len(new),
            "resolved": len(resolved),
            "recurring": len(recurring),
            "total_current": len(current),
            "total_previous": len(previous),
        },
    }


async def update_history(state: ScanState) -> ScanState:
    scan_id = state["scan_id"]
    domain = state.get("domain") or ""
    if not domain:
        return state

    async with session_scope() as session:
        prev_scans = await list_scans_for_domain(session, domain, exclude_id=scan_id)
        # Skip scans that themselves haven't succeeded/partial.
        prev: Scan | None = next(
            (
                s
                for s in prev_scans
                if s.status in ("succeeded", "partial")
            ),
            None,
        )
        if not prev:
            return state

        current = await get_findings(session, scan_id)
        previous = await get_findings(session, prev.id)
        summary = _diff_summaries(current, previous)
        summary["score_delta"] = (
            None if state.get("score") is None or prev.score is None
            else round(float(state["score"]) - float(prev.score), 2)
        )
        await save_comparison(session, scan_id, prev.id, summary)
        _log.info("compare saved: %s vs %s (delta=%s)", scan_id, prev.id, summary["delta"])
    return state
