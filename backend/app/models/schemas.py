"""Pydantic request / response schemas for the API."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, HttpUrl


Severity = Literal["critical", "serious", "moderate", "minor"]
Confidence = Literal["high", "medium", "low"]
ScanStatus = Literal["pending", "running", "succeeded", "failed", "partial"]


class ScanCreate(BaseModel):
    root_url: HttpUrl
    crawl_depth: int = Field(1, ge=0, le=3)
    page_limit: int = Field(5, ge=1, le=25)
    use_secondary: bool = True
    store_screenshots: bool = True
    strict_mode: bool = False


class WcagReference(BaseModel):
    criterion: str  # e.g. "1.1.1 Non-text Content"
    level: Optional[str] = None  # A | AA | AAA
    url: Optional[str] = None
    snippet: Optional[str] = None


class Remediation(BaseModel):
    explanation: str
    why_it_matters: str
    how_to_fix: str
    code_snippet: Optional[str] = None
    implementation_notes: Optional[str] = None
    grounded: bool = False


class FindingOut(BaseModel):
    id: str
    rule_id: str
    title: str
    severity: Severity
    source: str
    confidence: Confidence
    page_url: str
    selector: Optional[str] = None
    html_snippet: Optional[str] = None
    description: Optional[str] = None
    help_text: Optional[str] = None
    help_url: Optional[str] = None
    bbox: Optional[Dict[str, float]] = None
    annotated_screenshot_url: Optional[str] = None
    wcag_refs: List[WcagReference] = Field(default_factory=list)
    remediation: Optional[Remediation] = None


class PageOut(BaseModel):
    id: str
    url: str
    final_url: Optional[str] = None
    title: Optional[str] = None
    http_status: Optional[int] = None
    status: str
    error: Optional[str] = None
    screenshot_url: Optional[str] = None
    findings_count: int = 0


class ScanOut(BaseModel):
    id: str
    domain: str
    root_url: str
    status: ScanStatus
    created_at: datetime
    updated_at: datetime
    score: Optional[float] = None
    grade: Optional[str] = None
    executive_summary: Optional[str] = None
    stats: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    pages_count: int = 0
    findings_count: int = 0


class ScanDetail(ScanOut):
    pages: List[PageOut] = Field(default_factory=list)


class FindingsByPage(BaseModel):
    page: PageOut
    findings: List[FindingOut]


class ScanFindings(BaseModel):
    scan_id: str
    pages: List[FindingsByPage]


class ScanListItem(BaseModel):
    id: str
    domain: str
    root_url: str
    status: ScanStatus
    created_at: datetime
    score: Optional[float] = None
    grade: Optional[str] = None
    findings_count: int = 0


class CompareResult(BaseModel):
    scan_id: str
    previous_scan_id: str
    new_issues: List[Dict[str, Any]]
    resolved_issues: List[Dict[str, Any]]
    recurring_issues: List[Dict[str, Any]]
    delta: Dict[str, int]
    score_delta: Optional[float] = None


class PublicConfig(BaseModel):
    app_env: str
    model_provider: str
    model_name: str
    llm_enabled: bool
    embeddings_provider: str
    default_crawl_depth: int
    default_page_limit: int


class WcagSearchHit(BaseModel):
    criterion: str
    url: Optional[str] = None
    snippet: str
    score: float
