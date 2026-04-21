"""Typed state object passed between LangGraph nodes."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


class PlannedPage(TypedDict, total=False):
    url: str
    priority: int
    reason: str


class PageCapture(TypedDict, total=False):
    page_id: str
    url: str
    final_url: Optional[str]
    title: Optional[str]
    http_status: Optional[int]
    html: Optional[str]
    screenshot_path: Optional[str]
    interactive_selectors: List[str]
    axe_results: Optional[Dict[str, Any]]
    status: str  # ok | error | partial
    error: Optional[str]


class RawFinding(TypedDict, total=False):
    # Harmonised finding shape used downstream.
    rule_id: str
    title: str
    description: Optional[str]
    help_text: Optional[str]
    help_url: Optional[str]
    severity: str  # critical | serious | moderate | minor
    source: str   # axe | secondary
    selector: Optional[str]
    html_snippet: Optional[str]
    page_id: str
    page_url: str
    confidence: str  # high | medium | low
    wcag_refs: List[Dict[str, Any]]
    remediation: Optional[Dict[str, Any]]
    bbox: Optional[Dict[str, float]]
    annotated_screenshot_path: Optional[str]


class ScanState(TypedDict, total=False):
    scan_id: str
    root_url: str
    domain: str
    options: Dict[str, Any]

    planned_pages: List[PlannedPage]
    captures: List[PageCapture]
    findings: List[RawFinding]

    score: Optional[float]
    grade: Optional[str]
    executive_summary: Optional[str]
    stats: Dict[str, Any]

    errors: List[str]
