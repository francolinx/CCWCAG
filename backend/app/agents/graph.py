"""LangGraph multi-agent orchestration.

Nodes (executed sequentially for a single scan):

    plan_crawl → crawl_and_scan → secondary_audit → attach_wcag_evidence
                → attach_visual_evidence → generate_remediations
                → synthesize → persist_results → update_history

LangGraph is used here because it gives us:
  * typed state passing via TypedDict,
  * a declarative edge graph that is easy to extend with fan-out later
    (e.g. per-page annotation in parallel),
  * uniform error propagation per node.
"""
from __future__ import annotations

from typing import Any, Dict

from ..core.logging import get_logger
from .browser_crawl import crawl_and_scan
from .crawl_planner import plan_crawl
from .memory import update_history
from .persist import persist_results
from .remediation import generate_remediations
from .secondary_auditor import secondary_audit
from .state import ScanState
from .synthesis import synthesize
from .visual_evidence import attach_visual_evidence
from .wcag_research import attach_wcag_evidence

_log = get_logger(__name__)


def build_graph():
    from langgraph.graph import END, StateGraph

    g = StateGraph(ScanState)
    g.add_node("plan_crawl", plan_crawl)
    g.add_node("crawl_and_scan", crawl_and_scan)
    g.add_node("secondary_audit", secondary_audit)
    g.add_node("wcag_research", attach_wcag_evidence)
    g.add_node("visual_evidence", attach_visual_evidence)
    g.add_node("remediation", generate_remediations)
    g.add_node("synthesize", synthesize)
    g.add_node("persist", persist_results)
    g.add_node("memory", update_history)

    g.set_entry_point("plan_crawl")
    g.add_edge("plan_crawl", "crawl_and_scan")
    g.add_edge("crawl_and_scan", "secondary_audit")
    g.add_edge("secondary_audit", "wcag_research")
    g.add_edge("wcag_research", "visual_evidence")
    g.add_edge("visual_evidence", "remediation")
    g.add_edge("remediation", "synthesize")
    g.add_edge("synthesize", "persist")
    g.add_edge("persist", "memory")
    g.add_edge("memory", END)

    return g.compile()


async def run_scan_graph(initial: Dict[str, Any]) -> Dict[str, Any]:
    graph = build_graph()
    try:
        final = await graph.ainvoke(initial)
        return final
    except Exception as e:
        _log.exception("graph run failed: %s", e)
        raise
