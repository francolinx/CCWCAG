"""Browser Crawl Agent + Accessibility Scan Agent.

One pass through the planned pages. For each URL we:
  * load it with Playwright,
  * screenshot it,
  * inject axe-core and collect violations,
  * harmonise axe output into our RawFinding shape.

We keep the crawl and the axe run in the same agent because each Playwright
page context is the logical unit — separating them would force us to either
reload every URL (slow) or pass live page objects through state (brittle).
"""
from __future__ import annotations

from typing import Any, Dict, List

from ..core.logging import get_logger
from ..db.base import session_scope
from ..db.repository import create_page, update_page
from ..services.browser import BrowserService, PageCaptureResult
from .state import PageCapture, RawFinding, ScanState

_log = get_logger(__name__)


_SEVERITY_MAP = {
    "critical": "critical",
    "serious": "serious",
    "moderate": "moderate",
    "minor": "minor",
}


def _normalize_axe_severity(impact: Any) -> str:
    if not impact:
        return "minor"
    return _SEVERITY_MAP.get(str(impact).lower(), "minor")


def _axe_to_raw_findings(
    axe_results: Dict[str, Any], *, page_id: str, page_url: str
) -> List[RawFinding]:
    out: List[RawFinding] = []
    if not axe_results or axe_results.get("error"):
        return out
    for v in axe_results.get("violations", []) or []:
        rule_id = v.get("id") or "unknown"
        title = v.get("help") or v.get("description") or rule_id
        help_url = v.get("helpUrl")
        desc = v.get("description")
        severity = _normalize_axe_severity(v.get("impact"))
        for node in v.get("nodes", []) or []:
            selector = None
            targets = node.get("target") or []
            if targets:
                selector = targets[0] if isinstance(targets[0], str) else ", ".join(targets[0])
            html_snippet = node.get("html")
            out.append(
                RawFinding(
                    rule_id=rule_id,
                    title=title,
                    description=desc,
                    help_text=node.get("failureSummary") or v.get("help"),
                    help_url=help_url,
                    severity=severity,
                    source="axe",
                    selector=selector,
                    html_snippet=html_snippet,
                    page_id=page_id,
                    page_url=page_url,
                    confidence="high",
                    wcag_refs=[],
                    remediation=None,
                    bbox=None,
                    annotated_screenshot_path=None,
                )
            )
    return out


async def crawl_and_scan(state: ScanState) -> ScanState:
    scan_id = state["scan_id"]
    planned = state.get("planned_pages") or []
    opts = state.get("options") or {}
    store_screenshots = bool(opts.get("store_screenshots", True))

    captures: List[PageCapture] = []
    findings: List[RawFinding] = []

    async with BrowserService() as browser:
        for entry in planned:
            url = entry["url"]
            # Reserve a page row early so we have a stable id.
            async with session_scope() as session:
                page = await create_page(
                    session,
                    scan_id=scan_id,
                    url=url,
                    priority=int(entry.get("priority") or 0),
                    status="running",
                )
                page_id = page.id

            try:
                cap: PageCaptureResult = await browser.capture(
                    url,
                    scan_id=scan_id,
                    page_id=page_id,
                    store_screenshot=store_screenshots,
                )
            except Exception as e:  # never let one page take down the scan
                _log.warning("crawl failed for %s: %s", url, e)
                async with session_scope() as session:
                    await update_page(session, page_id, status="error", error=str(e))
                state.setdefault("errors", []).append(f"crawl:{url}:{e}")
                continue

            captures.append(
                PageCapture(
                    page_id=page_id,
                    url=url,
                    final_url=cap.final_url,
                    title=cap.title,
                    http_status=cap.http_status,
                    html=cap.html,
                    screenshot_path=cap.screenshot_path,
                    interactive_selectors=cap.interactive_selectors,
                    axe_results=cap.axe_results,
                    status=cap.status,
                    error=cap.error,
                )
            )

            async with session_scope() as session:
                await update_page(
                    session,
                    page_id,
                    final_url=cap.final_url,
                    title=cap.title,
                    http_status=cap.http_status,
                    screenshot_path=cap.screenshot_path,
                    status="ok" if cap.status == "ok" else cap.status,
                    error=cap.error,
                )

            if cap.axe_results:
                findings.extend(
                    _axe_to_raw_findings(
                        cap.axe_results,
                        page_id=page_id,
                        page_url=cap.final_url or url,
                    )
                )

    state["captures"] = captures
    state["findings"] = findings
    _log.info(
        "crawl+axe done: %d pages captured, %d axe findings", len(captures), len(findings)
    )
    return state
