"""Crawl Planner Agent.

Inputs: root URL + options. Output: prioritized list of pages to scan.

Strategy:
  1. Visit the root URL in a headless browser, grab on-domain links from the
     rendered DOM (this captures JS-injected nav / footer links).
  2. Score each candidate with a priority heuristic.
  3. Optionally refine ordering with the LLM if one is configured.
  4. Always include the root URL first, and cap at `page_limit`.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List

from ..core.logging import get_logger
from ..services.browser import BrowserService
from ..services.llm import get_llm
from ..utils.url import (
    canonical_domain,
    dedupe_preserving_order,
    normalize_url,
    same_site,
    score_candidate,
)
from .prompts import CRAWL_PLANNER_SYSTEM
from .state import PlannedPage, ScanState

_log = get_logger(__name__)


async def _candidate_links(browser: BrowserService, root_url: str) -> List[str]:
    """Use the root page's rendered DOM to enumerate candidate on-domain links."""
    capture = await browser.capture(
        root_url, scan_id="planner", page_id="root", store_screenshot=False
    )
    links: List[str] = []
    html = capture.html or ""
    if html:
        # A quick regex pass is enough — we just want hrefs.
        import re

        for m in re.finditer(r'href=["\']([^"\']+)["\']', html, flags=re.IGNORECASE):
            href = m.group(1)
            norm = normalize_url(root_url, href)
            if norm and same_site(norm, root_url):
                links.append(norm)
    return dedupe_preserving_order(links)


async def plan_crawl(state: ScanState) -> ScanState:
    root_url = state["root_url"]
    opts = state.get("options") or {}
    page_limit = int(opts.get("page_limit") or 5)
    depth = int(opts.get("crawl_depth") or 1)

    async with BrowserService() as browser:
        candidates = await _candidate_links(browser, root_url)

    # Always include the root page first at priority 100.
    scored: List[Dict[str, Any]] = [
        {"url": root_url, "priority": 100, "reason": "homepage"}
    ]
    seen = {root_url}
    for url in candidates:
        if url in seen:
            continue
        scored.append(
            {
                "url": url,
                "priority": max(1, score_candidate(url)),
                "reason": "heuristic",
            }
        )
        seen.add(url)

    # Depth 0 means "root only".
    if depth == 0:
        planned: List[PlannedPage] = [scored[0]]
    else:
        scored.sort(key=lambda x: x["priority"], reverse=True)

        # LLM refinement is optional — we still rely on the heuristic for correctness.
        llm = get_llm()
        if llm.enabled and len(scored) > page_limit:
            trimmed = scored[: min(30, len(scored))]
            payload = {
                "root_url": root_url,
                "domain": canonical_domain(root_url),
                "page_limit": page_limit,
                "candidates": trimmed,
            }
            obj = llm.json_complete(
                system=CRAWL_PLANNER_SYSTEM,
                user=json.dumps(payload),
                temperature=0.2,
                max_tokens=500,
            )
            if obj and isinstance(obj.get("pages"), list):
                valid = {c["url"] for c in trimmed}
                refined: List[Dict[str, Any]] = []
                for p in obj["pages"]:
                    u = p.get("url")
                    if u in valid:
                        refined.append(
                            {
                                "url": u,
                                "priority": int(p.get("priority") or 50),
                                "reason": p.get("reason") or "llm",
                            }
                        )
                if refined:
                    if not any(r["url"] == root_url for r in refined):
                        refined.insert(0, scored[0])
                    scored = refined

        planned = scored[:page_limit]

    state["planned_pages"] = planned
    state.setdefault("errors", [])
    _log.info("planner chose %d pages for %s", len(planned), root_url)
    return state
