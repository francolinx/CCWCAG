"""WCAG Research Agent.

Uses the RAG retriever to fetch grounded WCAG evidence for each finding.
Every attached reference includes the official W3C canonical URL from the
corpus metadata — never fabricated.
"""
from __future__ import annotations

from typing import Dict, List

from ..core.logging import get_logger
from ..rag.retriever import RetrievedChunk, get_retriever
from .state import RawFinding, ScanState

_log = get_logger(__name__)


def _query_for(f: RawFinding) -> str:
    parts = [f.get("rule_id") or "", f.get("title") or "", f.get("description") or ""]
    return " ".join(p for p in parts if p)[:500]


def _to_refs(chunks: List[RetrievedChunk]) -> List[Dict]:
    refs: List[Dict] = []
    seen = set()
    for c in chunks:
        crit = c.metadata.get("criterion") or c.metadata.get("criterion_title") or "WCAG"
        if crit in seen:
            continue
        seen.add(crit)
        refs.append(
            {
                "criterion": crit,
                "level": c.metadata.get("level"),
                "url": c.metadata.get("url"),
                "snippet": c.text[:600],
                "score": round(c.score, 3),
            }
        )
    return refs


async def attach_wcag_evidence(state: ScanState) -> ScanState:
    retriever = get_retriever()
    if not retriever.ready:
        _log.info("WCAG index not ready — skipping grounding (remediation will be un-grounded)")
        return state

    findings = state.get("findings") or []
    # Cache retrievals by rule_id to avoid re-querying the same rule 50x.
    cache: Dict[str, List[Dict]] = {}
    for f in findings:
        key = f.get("rule_id") or _query_for(f)
        if key not in cache:
            hits = retriever.search(_query_for(f), top_k=3)
            cache[key] = _to_refs(hits)
        f["wcag_refs"] = cache[key]
    _log.info("attached WCAG refs to %d findings", len(findings))
    return state
