"""Visual Evidence Agent.

Resolves each finding's CSS selector in a fresh Playwright page, grabs the
bounding box, and uses the annotation pipeline to draw a highlighted box on
a copy of the screenshot. Failures degrade gracefully (finding simply stays
un-annotated).

To keep wall-clock time reasonable we cap the number of annotations per page
(the top N by severity) since many pages have dozens of findings from the
same violation.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List

from ..core.logging import get_logger
from ..services.annotation import annotate_finding
from ..services.browser import BrowserService
from .state import PageCapture, RawFinding, ScanState

_log = get_logger(__name__)

_SEVERITY_ORDER = {"critical": 0, "serious": 1, "moderate": 2, "minor": 3}
_MAX_ANNOTATED_PER_PAGE = 8


def _sort_key(f: RawFinding) -> int:
    return _SEVERITY_ORDER.get(f.get("severity", "minor"), 3)


async def attach_visual_evidence(state: ScanState) -> ScanState:
    findings: List[RawFinding] = state.get("findings") or []
    captures: List[PageCapture] = state.get("captures") or []
    if not findings or not captures:
        return state

    cap_by_page: Dict[str, PageCapture] = {c["page_id"]: c for c in captures if "page_id" in c}

    # Group findings by page, take top-N per page.
    to_process: Dict[str, List[RawFinding]] = defaultdict(list)
    for f in findings:
        to_process[f["page_id"]].append(f)
    for pid, items in to_process.items():
        items.sort(key=_sort_key)
        to_process[pid] = items[:_MAX_ANNOTATED_PER_PAGE]

    async with BrowserService() as browser:
        for page_id, items in to_process.items():
            cap = cap_by_page.get(page_id)
            if not cap:
                continue
            screenshot = cap.get("screenshot_path")
            url = cap.get("final_url") or cap.get("url")
            if not screenshot or not url:
                continue
            for idx, f in enumerate(items):
                sel = f.get("selector")
                if not sel:
                    continue
                try:
                    bbox = await browser.get_bbox(url, sel)
                except Exception as e:
                    _log.debug("bbox lookup error for %s: %s", sel, e)
                    bbox = None
                if not bbox:
                    continue
                ann = annotate_finding(
                    screenshot_path=screenshot,
                    bbox=bbox,
                    rule_id=f.get("rule_id", "rule"),
                    severity=f.get("severity", "minor"),
                    out_name=f"{state['scan_id']}_{page_id}_{idx}_{f.get('rule_id','rule')}.png",
                )
                f["bbox"] = bbox
                f["annotated_screenshot_path"] = ann.annotated_path
    return state
